from pdfrw import PdfReader, PdfWriter, PdfDict, PdfObject
import os


def compila_pdf_con_acroform(dati, giro_id):
    input_pdf = 'static/pdf/modulo_fir.pdf'
    nome_file = f"FIR_{dati['cliente'].replace(' ', '_')}_{giro_id}.pdf"
    output_dir = 'static/formulari/'
    os.makedirs(output_dir, exist_ok=True)
    output_pdf = os.path.join(output_dir, nome_file)

    pdf = PdfReader(input_pdf)

    # 🔥 Forza aggiornamento dell'aspetto dei campi
    if not hasattr(pdf.Root, 'AcroForm'):
        pdf.Root.AcroForm = PdfDict()

    pdf.Root.AcroForm.update(PdfDict(
        NeedAppearances=PdfObject('true'),
        DA=PdfObject("/Helv 7 Tf 0 g")
    ))


    for page in pdf.pages:
        annotations = page.Annots
        if annotations:
            for annot in annotations:
                if annot.T:
                    campo = annot.T[1:-1]
                    if campo in dati:
                        annot.V = PdfObject('({})'.format(dati[campo]))
                        annot.AP = None  # importante per renderizzare

    PdfWriter().write(output_pdf, pdf)
    return output_pdf
