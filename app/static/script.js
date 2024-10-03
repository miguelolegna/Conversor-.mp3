document.getElementById('converter-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const spotifyUrl = document.getElementById('spotify-url').value;
    const resultDiv = document.getElementById('result');
    
    resultDiv.innerHTML = 'Convertendo...';
    
    try {
        const response = await fetch(`/convert?spotify_url=${encodeURIComponent(spotifyUrl)}`);
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'music.mp3';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            resultDiv.innerHTML = 'Conversão concluída! O download deve começar automaticamente.';
        } else {
            const errorData = await response.json();
            resultDiv.innerHTML = `Erro: ${errorData.detail}`;
        }
    } catch (error) {
        resultDiv.innerHTML = `Erro: ${error.message}`;
    }
});