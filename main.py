import os

DATA_DIR = "data"
OUTPUT_DIR = "output"

def dosyalari_listele():
    files = os.listdir(DATA_DIR)
    print("Bulunan dosyalar:")
    for f in files:
        print("-", f)
    return files

def main():
    print("TJK Parser Başlatıldı\n")

    if not os.path.exists(DATA_DIR):
        print("data klasörü yok!")
        return

    files = dosyalari_listele()

    if not files:
        print("Hiç veri yok!")
        return

    print("\nHazırız. Codex ile geliştirebiliriz.")

if __name__ == "__main__":
    main()