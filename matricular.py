import os
import threading
from typing import List, Tuple, Optional
import requests
from fastapi import APIRouter, HTTPException
from datetime import datetime

router = APIRouter()

# Variáveis de ambiente
BASIC_B64 = os.getenv("BASIC_B64")
UNIDADE_ID = os.getenv("UNIDADE_ID")
OM_BASE = os.getenv("OM_BASE")

# Bloqueio para gerar CPF sequencial
CPF_PREFIXO = "20254158"
cpf_lock = threading.Lock()


def _log(msg: str):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{agora}] {msg}")


def _obter_token_unidade() -> str:
    """
    Faz GET em /unidades/token/{UNIDADE_ID} para obter token OM.
    """
    if not all([OM_BASE, BASIC_B64, UNIDADE_ID]):
        raise RuntimeError("Variáveis de ambiente OM não configuradas.")
    url = f"{OM_BASE}/unidades/token/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        return r.json()["data"]["token"]
    raise RuntimeError(f"Falha ao obter token da unidade: {r.status_code}")


def _total_alunos() -> int:
    """
    Retorna total de alunos cadastrado na unidade OM (para gerar CPF).
    """
    url = f"{OM_BASE}/alunos/total/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        return int(r.json()["data"]["total"])
    # fallback
    url2 = f"{OM_BASE}/alunos?unidade_id={UNIDADE_ID}&cpf_like={CPF_PREFIXO}"
    r2 = requests.get(url2, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r2.ok and r2.json().get("status") == "true":
        return len(r2.json()["data"])
    raise RuntimeError("Falha ao apurar total de alunos")


def _proximo_cpf(incremento: int = 0) -> str:
    with cpf_lock:
        seq = _total_alunos() + 1 + incremento
        return CPF_PREFIXO + str(seq).zfill(3)


def _cadastrar_somente_aluno(
    nome: str, whatsapp: str, email: Optional[str], token_key: str, senha_padrao: str = "123456"
) -> Tuple[str, str]:
    """
    Cadastra apenas o aluno (sem matrícula em disciplinas).
    Retorna (aluno_id, cpf).
    """
    for tentativa in range(60):
        cpf = _proximo_cpf(tentativa)
        payload = {
            "token": token_key,
            "nome": nome,
            "email": email or "",
            "whatsapp": whatsapp,
            "fone": whatsapp,
            "celular": whatsapp,
            "data_nascimento": "2000-01-01",
            "doc_cpf": cpf,
            "doc_rg": "000000000",
            "pais": "Brasil",
            "uf": "DF",
            "cidade": "Brasília",
            "endereco": "Não informado",
            "bairro": "Centro",
            "cep": "70000-000",
            "complemento": "",
            "numero": "0",
            "unidade_id": UNIDADE_ID,
            "senha": senha_padrao,
        }
        r = requests.post(
            f"{OM_BASE}/alunos",
            data=payload,
            headers={"Authorization": f"Basic {BASIC_B64}"},
            timeout=10,
        )
        _log(f"[CAD] Tentativa {tentativa+1}/60 | Status {r.status_code}")
        if r.ok and r.json().get("status") == "true":
            aluno_id = r.json()["data"]["id"]
            return aluno_id, cpf

        info = (r.json() or {}).get("info", "").lower()
        if "já está em uso" not in info:
            break

    raise RuntimeError("Falha ao cadastrar o aluno")


def _matricular_aluno_om(aluno_id: str, cursos_ids: List[int], token_key: str) -> bool:
    """
    Efetua a matrícula (vincula disciplinas) para o aluno já cadastrado.
    """
    if not cursos_ids:
        # Se não há cursos a matricular, pulamos este passo
        _log(f"[MAT] Nenhum curso informado para aluno {aluno_id}. Pulando matrícula.")
        return True

    cursos_str = ",".join(map(str, cursos_ids))
    payload = {"token": token_key, "cursos": cursos_str}
    _log(f"[MAT] Matriculando aluno {aluno_id} nos cursos: {cursos_str}")
    r = requests.post(
        f"{OM_BASE}/alunos/matricula/{aluno_id}",
        data=payload,
        headers={"Authorization": f"Basic {BASIC_B64}"},
        timeout=10,
    )
    sucesso = r.ok and r.json().get("status") == "true"
    _log(f"[MAT] {'✅' if sucesso else '❌'} Status {r.status_code}")
    return sucesso


def _cadastrar_aluno_om(
    nome: str,
    whatsapp: str,
    email: Optional[str],
    cursos_ids: List[int],
    token_key: str,
    senha_padrao: str = "123456",
) -> Tuple[str, str]:
    """
    Cadastra aluno e, se houver cursos_ids, matrícula nas disciplinas.
    Retorna (aluno_id, cpf).
    """
    # Primeiro, cadastro sem matrícula
    aluno_id, cpf = _cadastrar_somente_aluno(nome, whatsapp, email, token_key, senha_padrao)

    # Se houver cursos, tenta matricular. Se não houver, considera sucesso.
    if cursos_ids:
        ok_matri = _matricular_aluno_om(aluno_id, cursos_ids, token_key)
        if not ok_matri:
            raise RuntimeError("Aluno cadastrado, mas falha ao matricular em disciplinas.")
    else:
        _log(f"[MAT] Curso não informado para {nome}. Cadastro concluído sem matrícula.")

    return aluno_id, cpf


@router.post("/", summary="Cadastra (e opcionalmente matricula) um aluno na OM")
async def realizar_matricula(dados: dict):
    """
    Espera um JSON com:
      - nome: str (obrigatório)
      - whatsapp: str (obrigatório)
      - email: str (opcional)
      - cursos_ids: List[int] (opcional, IDs de disciplinas)
    Exemplo de body mínimo:
    {
      "nome": "Maria Silva",
      "whatsapp": "61988887777"
    }

    Exemplo com cursos:
    {
      "nome": "Maria Silva",
      "whatsapp": "61988887777",
      "email": "maria@ex.com",
      "cursos_ids": [129, 198, 156, 154]
    }
    """
    nome = dados.get("nome")
    whatsapp = dados.get("whatsapp")
    email = dados.get("email")
    cursos_ids = dados.get("cursos_ids") or []

    # Validações: apenas nome e whatsapp são obrigatórios
    if not nome or not whatsapp:
        raise HTTPException(status_code=400, detail="Dados incompletos: 'nome' e 'whatsapp' são obrigatórios.")

    try:
        token_unit = _obter_token_unidade()
        aluno_id, cpf = _cadastrar_aluno_om(nome, whatsapp, email, cursos_ids, token_unit)
        return {
            "status": "ok",
            "aluno_id": aluno_id,
            "cpf": cpf,
            "disciplinas_matriculadas": cursos_ids,
        }
    except Exception as e:
        _log(f"❌ Erro em /matricular: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
