import os
import shutil
import uuid

from django import forms
from django.conf import settings


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True


class SetupForm(forms.Form):
    signature = forms.ImageField(
        required=False,
        label="Upload signature image",
        help_text="PNG (transparent) or JPG. Optional if signature path is set.",
    )
    signature_path = forms.CharField(
        required=False,
        label="Or signature file path",
        help_text="Example: E:\\signs\\mysign.png",
        widget=forms.TextInput(attrs={"placeholder": r"E:\path\to\signature.png"}),
    )
    sample_pdf = forms.FileField(
        required=False,
        label="Upload sample PDF (for page preview)",
        help_text="Used to preview pages and set signature position on each page.",
        widget=forms.FileInput(attrs={"accept": "application/pdf"}),
    )
    extra_pdfs = forms.FileField(
        required=False,
        label="Upload more PDFs to sign (optional)",
        help_text="All these PDFs get the same per-page positions as the sample.",
        widget=MultipleFileInput(attrs={"multiple": True, "accept": "application/pdf"}),
    )
    input_path = forms.CharField(
        required=False,
        label="Main PDF path (file or folder)",
        help_text="PDF file path, or a folder of PDFs to sign with the same positions.",
        widget=forms.TextInput(
            attrs={"placeholder": r"E:\pdfs\contract.pdf  or  E:\pdfs\inbox"}
        ),
    )
    output_path = forms.CharField(
        required=True,
        label="Output folder path",
        help_text="Signed PDFs will be saved here.",
        widget=forms.TextInput(attrs={"placeholder": r"E:\pdfs\signed"}),
    )

    def __init__(self, *args, **kwargs):
        super(SetupForm, self).__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["output_path"].initial = os.path.join(
                settings.MEDIA_ROOT, "output"
            )
            default_sig = getattr(settings, "SIGNATURE_IMAGE_PATH", "")
            if default_sig and os.path.isfile(default_sig):
                self.fields["signature_path"].initial = default_sig

    def clean(self):
        cleaned = super(SetupForm, self).clean()
        sample = cleaned.get("sample_pdf")
        input_path = (cleaned.get("input_path") or "").strip().strip('"')
        signature = cleaned.get("signature")
        signature_path = (cleaned.get("signature_path") or "").strip().strip('"')
        output_path = (cleaned.get("output_path") or "").strip().strip('"')

        cleaned["input_path"] = input_path
        cleaned["signature_path"] = signature_path
        cleaned["output_path"] = output_path

        # extra_pdfs may be present in FILES even if not in cleaned
        has_extra = False
        if hasattr(self, "files"):
            has_extra = bool(self.files.getlist("extra_pdfs"))

        if not sample and not input_path and not has_extra:
            raise forms.ValidationError(
                "Provide a sample PDF upload, extra PDFs, and/or a main PDF path."
            )

        if input_path and not (os.path.isfile(input_path) or os.path.isdir(input_path)):
            raise forms.ValidationError(
                "Main PDF path does not exist: {}".format(input_path)
            )

        if input_path and os.path.isfile(input_path) and not input_path.lower().endswith(
            ".pdf"
        ):
            raise forms.ValidationError("Main PDF path must be a .pdf file or a folder.")

        if not signature and not signature_path:
            raise forms.ValidationError(
                "Upload a signature image or enter a signature file path."
            )
        if signature_path and not os.path.isfile(signature_path):
            raise forms.ValidationError(
                "Signature path not found: {}".format(signature_path)
            )

        if not output_path:
            raise forms.ValidationError("Output folder path is required.")

        return cleaned


def new_job_dir():
    job_id = uuid.uuid4().hex[:12]
    root = os.path.join(settings.MEDIA_ROOT, "jobs", job_id)
    os.makedirs(root, exist_ok=True)
    return job_id, root


def save_upload(uploaded, dest_path):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as out:
        for chunk in uploaded.chunks():
            out.write(chunk)
    return dest_path


def copy_file(src, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(src, dest)
    return dest
