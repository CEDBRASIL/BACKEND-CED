const API_BASE = "https://api.cedbrasilia.com.br";

document.addEventListener("DOMContentLoaded", () => listarCursos());

function listarCursos() {
  fetch(API_BASE + "/cursos")
    .then(r => r.json())
    .then(json => {
      const container = document.getElementById("cursosContainer");
      container.innerHTML = "";
      Object.keys(json.cursos).forEach(nome => {
        const id = "curso-" + nome.replace(/\s+/g, "-");
        container.insertAdjacentHTML(
          "beforeend",
          `<label><input type="checkbox" name="cursos" value="${nome}" id="${id}"> ${nome}</label>`
        );
      });
    })
    .catch(() => {
      document.getElementById("cursosContainer").textContent = "Erro ao carregar cursos.";
    });
}

document.getElementById("matriculaForm").addEventListener("submit", e => {
  e.preventDefault();

  const nome      = document.getElementById("nome").value.trim();
  const email     = document.getElementById("email").value.trim();
  const whatsapp  = document.getElementById("whatsapp").value.trim().replace(/\D/g,"");
  const cursos    = Array.from(document.querySelectorAll("input[name='cursos']:checked")).map(c => c.value);

  if (!nome || !email || !whatsapp || cursos.length === 0) {
    alert("Preencha todos os campos e selecione ao menos um curso.");
    return;
  }

  fetch(API_BASE + "/pay/eeb/checkout", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ nome, email, whatsapp, cursos })
  })
  .then(r => r.json())
  .then(json => {
    if (json.mp_link) {
      window.location.href = json.mp_link;
    } else {
      alert(json.detail || "Falha ao gerar link de pagamento.");
    }
  })
  .catch(() => alert("Erro de comunicação com o servidor."));
});
