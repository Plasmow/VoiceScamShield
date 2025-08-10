
import requests
import base64

def get_filtered_chunks():
    resp = requests.get("http://localhost:8080/chunks")
    resp.raise_for_status()
    data = resp.json()
    chunks = [base64.b64decode(c) for c in data["chunks"]]
    return chunks

if __name__ == "__main__":
    chunks = get_filtered_chunks()
    print(f"Reçu {len(chunks)} chunks filtrés")
    # Exemple : sauvegarder le premier chunk dans un fichier .raw
    if chunks:
        with open("chunk.raw", "wb") as f:
            f.write(chunks[0])
