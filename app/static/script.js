// Função para adicionar evento de clique e redirecionamento
function addClickEvent(id, url) {
    var imagem = document.getElementById(id);
    if (imagem) {
        imagem.addEventListener("click", function() {
            window.location.href = url;
        });
    } else {
        console.error("Elemento não encontrado: " + id);
    }
}


