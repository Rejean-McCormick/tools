import os
import tkinter as tk
from tkinter import filedialog, messagebox

from docx import Document  # pip install python-docx


def docx_to_markdown(docx_path: str) -> str:
    """Conversion simple .docx -> markdown (titres, listes, paragraphes)."""
    doc = Document(docx_path)
    lines = []

    for para in doc.paragraphs:
        # Texte brut du paragraphe (sans gérer gras/italique pour rester simple)
        text = "".join(run.text for run in para.runs).strip()

        # Ligne vide
        if not text:
            lines.append("")
            continue

        style_name = para.style.name if para.style is not None else ""

        # Titres (Heading 1, Heading 2, etc.)
        if style_name.startswith("Heading"):
            # Récupère le niveau (1, 2, 3...) s’il existe
            level = 1
            for part in style_name.split():
                if part.isdigit():
                    level = int(part)
                    break
            lines.append("#" * level + " " + text)

        # Listes (styles Word classiques : List Bullet, List Number, etc.)
        elif style_name.startswith("List"):
            lines.append(f"- {text}")

        # Paragraphe normal
        else:
            lines.append(text)

    return "\n".join(lines)


def select_and_convert():
    filepath = filedialog.askopenfilename(
        title="Choisir un fichier .docx",
        filetypes=[("Fichiers Word", "*.docx"), ("Tous les fichiers", "*.*")],
    )

    if not filepath:
        return  # l'utilisateur a annulé

    try:
        md_text = docx_to_markdown(filepath)

        base, _ = os.path.splitext(filepath)
        md_path = base + ".md"

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_text)

        messagebox.showinfo(
            "Conversion terminée",
            f"Le fichier Markdown a été enregistré sous :\n{md_path}",
        )
    except Exception as e:
        messagebox.showerror("Erreur", f"Une erreur est survenue :\n{e}")


def main():
    root = tk.Tk()
    root.title("Convertisseur DOCX -> Markdown")
    root.geometry("420x180")

    label = tk.Label(
        root,
        text="Sélectionner un fichier .docx à convertir en .md",
        wraplength=380,
        justify="center",
    )
    label.pack(pady=20)

    btn = tk.Button(
        root,
        text="Choisir un .docx et convertir",
        command=select_and_convert,
        width=30,
        height=2,
    )
    btn.pack(pady=10)

    root.mainloop()


if __name__ == "__main__":
    main()
