import os
import requests
from fastapi import APIRouter, HTTPException
from typing import Dict, List
from datetime import datetime

router = APIRouter()

# Consulta dos tokens (caso precise autenticar na OM)
BASIC_B64 = os.getenv("BASIC_B64")
UNIDADE_ID = os.getenv("UNIDADE_ID")
OM_BASE = os.getenv("OM_BASE")

# Mapeamento de cursos para IDs de disciplinas da OM
CURSOS_OM: Dict[str, List[int]] = {
    "Excel PRO": [161, 197, 201],
    "Design Gráfico": [254, 751, 169],
    "Analista e Desenvolvimento de Sistemas": [590, 176, 239, 203],
    "Administração": [129, 198, 156, 154],
    "Inglês Fluente": [263, 280, 281],
    "Inglês Kids": [266],
    "Informática Essencial": [130, 599, 161, 160, 162],
    "Operador de Micro": [130, 599, 160, 161, 162, 163, 222],
    "Especialista em Marketing & Vendas 360º": [123, 199, 202, 236, 264, 441, 734, 780, 828, 829],
    "Marketing Digital": [734, 236, 441, 199, 780],
    "Pacote Office": [160, 161, 162, 197, 201],
}

def _log(msg: str):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{agora}] {msg}")

@router.get("/", summary="Lista todos os cursos disponíveis")
async def listar_cursos():
    """
    Retorna um dicionário com todos os cursos e seus respectivos IDs de disciplinas.
    """
    return {"cursos": CURSOS_OM}

@router.get("/{nome_curso}", summary="Obtém os IDs de disciplinas de um curso específico")
async def obter_ids_curso(nome_curso: str):
    """
    Consulta o mapeamento CURSOS_OM e devolve a lista de IDs de disciplinas para o curso solicitado.
    Exemplo de URL: /cursos/Administração
    """
    curso_key = next((k for k in CURSOS_OM if k.lower() == nome_curso.lower()), None)
    if not curso_key:
        raise HTTPException(status_code=404, detail=f"Curso '{nome_curso}' não encontrado.")
    return {"curso": curso_key, "disciplinas": CURSOS_OM[curso_key]}

@router.get("/tokens", summary="Exemplo: retornar token atual da unidade (opcional)")
async def consultar_token_unidade():
    """
    Exemplo de rota adicional em 'cursos' para verificar token da OM.
    """
    if not all([BASIC_B64, UNIDADE_ID, OM_BASE]):
        raise HTTPException(status_code=500, detail="Variáveis de ambiente OM não configuradas.")
    url = f"{OM_BASE}/unidades/token/{UNIDADE_ID}"
    r = requests.get(url, headers={"Authorization": f"Basic {BASIC_B64}"}, timeout=8)
    if r.ok and r.json().get("status") == "true":
        token = r.json()["data"]["token"]
        _log(f"Token obtido na rota /cursos/tokens: {token}")
        return {"status": "ok", "token": token}
    raise HTTPException(status_code=500, detail="Falha ao obter token da unidade.")
