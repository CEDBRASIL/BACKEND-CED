from fastapi import FastAPI

app = FastAPI()

from cursos import CURSOS_OM, listar_cursos
import os
import threading
import datetime
from typing import List, Tuple

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request    
import uvicorn

# Carrega variáveis de ambiente
load_dotenv()

OM_BASE         = os.getenv("OM_BASE")
BASIC_B64       = os.getenv("BASIC_B64")
UNIDADE_ID      = os.getenv("UNIDADE_ID")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")
DISCORD_FIXO    = "https://discord.com/api/webhooks/1377838283975036928/IgVvwyrBBWflKyXbIU9dgH4PhLwozHzrf-nJpj3w7dsZC-Ds9qN8_Toym3Tnbj-3jdU4"

CALLMEBOT_URL      = "https://api.callmebot.com/whatsapp.php"
CALLMEBOT_APIKEY   = "2712587"
CALLMEBOT_PHONE    = "+556186660241"

CPF_PREFIXO = "20254158"
cpf_lock = threading.Lock()

# ────────────────── Helpers ────────────────── #

def _log(msg: str) -> None:
    """Envia mensagens para console e, se configurado, para webhooks."""
    print(msg)
    for webhook in filter(None, (DISCORD_WEBHOOK, DISCORD_FIXO)):
        try:
            requests.post(webhook, json={"content": msg}, timeout=4)
        except Exception:
            pass

def _enviar_callmebot(msg: str) -> None:
    try:
        params = {
            "phone": CALLMEBOT_PHONE,
            "text": msg,
            "apikey": CALLMEBOT_APIKEY,
        }
        requests.get(CALLMEBOT_URL, params=params, timeout=10)
    except Exception:
        pass

def _obter_token_unidade() -> str:
    url = f"{OM_BASE}/unidades/token/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        return r.json()["data"]["token"]
    raise RuntimeError(f"Falha ao obter token da unidade: {r.status_code}")

def _total_alunos() -> int:
    url = f"{OM_BASE}/alunos/total/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        return int(r.json()["data"]["total"])
    # fallback
    url = f"{OM_BASE}/alunos?unidade_id={UNIDADE_ID}&cpf_like={CPF_PREFIXO}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        return len(r.json()["data"])
    raise RuntimeError("Falha ao apurar total de alunos")

def _proximo_cpf(incremento: int = 0) -> str:
    with cpf_lock:
        sequencia = _total_alunos() + 1 + incremento
        return CPF_PREFIXO + str(sequencia).zfill(3)

# ────────────────── Operações na OM ────────────────── #

def _matricular_aluno_om(aluno_id: str, cursos_ids: List[int], token_key: str) -> bool:
    """Efetua a matrícula (vincula planos) para o aluno já cadastrado."""
    cursos_ids = list(map(str, cursos_ids))
    if not cursos_ids:
        _log("[MAT] Nenhum curso informado.")
        return False

    payload = {"token": token_key, "cursos": ",".join(cursos_ids)}
    _log(f"[MAT] matriculando aluno {aluno_id} | cursos {payload['cursos']}")
    r = requests.post(
        f"{OM_BASE}/alunos/matricula/{aluno_id}",
        data=payload,
        headers={"Authorization": f"Basic {BASIC_B64}"},
        timeout=10,
    )
    sucesso = r.ok and r.json().get("status") == "true"
    _log(f"[MAT] {'✅' if sucesso else '❌'} {r.status_code} | {r.text[:120]}")
    return sucesso

def _cadastrar_aluno_om(
    nome: str,
    whatsapp: str,
    email: str,
    cursos_ids: List[int],
    token_key: str,
    senha_padrao: str = "123456",
) -> Tuple[str | None, str | None]:
    """Tenta cadastrar o aluno (até 60 tentativas com CPF sequencial)."""
    for tentativa in range(60):
        cpf = _proximo_cpf(tentativa)
        payload = {
            "token": token_key,
            "nome": nome,
            "email": email,
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
        _log(f"[CAD] tent {tentativa+1}/60 | {r.status_code} | {r.text[:120]}")
        if r.ok and r.json().get("status") == "true":
            aluno_id = r.json()["data"]["id"]
            if _matricular_aluno_om(aluno_id, cursos_ids, token_key):
                _enviar_callmebot("✅ Matrícula gerada com sucesso.")
                return aluno_id, cpf
        if "já está em uso" not in (r.json() or {}).get("info", "").lower():
            break
    return None, None

# ────────────────── API externa ────────────────── #

def matricular_aluno(
    nome: str,
    whatsapp: str,
    email: str,
    cursos_ids: List[int],
) -> Tuple[str, str]:
    if not cursos_ids:
        raise ValueError("'cursos_ids' não pode estar vazio.")

    token_key = _obter_token_unidade()
    aluno_id, cpf = _cadastrar_aluno_om(nome, whatsapp, email, cursos_ids, token_key)
    if not aluno_id:
        raise RuntimeError("Falha ao cadastrar ou matricular o aluno.")

    _log(f"✅ Processo concluído – aluno_id: {aluno_id} | cpf: {cpf}")
    return aluno_id, cpf

# ────────────────── API HTTP (gatilho) ────────────────── #

app = FastAPI()

@app.post("/matricular")
async def gatilho_matricula(request: Request):
    body = await request.json()

    nome = body.get("nome")
    whatsapp = body.get("whatsapp")
    email = body.get("email")
    cursos_ids = body.get("cursos_ids")  # lista de ints

    if not all([nome, whatsapp, email, cursos_ids]):
        return {"status": "erro", "mensagem": "Dados incompletos"}

    try:
        aluno_id, cpf = matricular_aluno(nome, whatsapp, email, cursos_ids)
        return {"status": "ok", "aluno_id": aluno_id, "cpf": cpf}
    except Exception as e:
        return {"status": "erro", "mensagem": str(e)}
    



# ────────────────── API Secure (gatilho para Renovar a token) ────────────────── #

@app.get("/secure")
async def renovar_token():
    try:
        _ = _obter_token_unidade()
        return {"status": "ok", "mensagem": "Token renovado com sucesso"}
    except Exception as e:
        return {"status": "erro", "mensagem": str(e)}



# ────────────────── CLI rápido ────────────────── #

if __name__ == "__main__":
    import argparse, sys, json

    parser = argparse.ArgumentParser(description="Matricula rápida de aluno")
    parser.add_argument("nome")
    parser.add_argument("whatsapp")
    parser.add_argument("email")
    parser.add_argument("cursos", help="Lista de IDs de planos, separada por vírgulas")

    args = parser.parse_args()
    ids = [int(i.strip()) for i in args.cursos.split(",") if i.strip().isdigit()]

    try:
        aluno_id, cpf = matricular_aluno(args.nome, args.whatsapp, args.email, ids)
        resultado = {"status": "ok", "aluno_id": aluno_id, "cpf": cpf}
    except Exception as e:
        resultado = {"status": "erro", "erro": str(e)}

    print(json.dumps(resultado, ensure_ascii=False, indent=2))

    # Iniciar servidor FastAPI local, se necessário
    # uvicorn.run(app, host="0.0.0.0", port=8000)


