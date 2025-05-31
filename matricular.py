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
            return aluno_id,_
