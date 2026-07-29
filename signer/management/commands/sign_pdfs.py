from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
import glob
import os

from signer.pdf_signer import stamp_many


class Command(BaseCommand):
    help = "Stamp the local signature onto all PDFs in a folder (or listed files)."

    def add_arguments(self, parser):
        parser.add_argument(
            "inputs",
            nargs="+",
            help="PDF file paths and/or folders containing PDFs",
        )
        parser.add_argument(
            "-o",
            "--output",
            default=None,
            help="Output folder (default: media/output)",
        )
        parser.add_argument(
            "--page",
            choices=["last", "first", "all"],
            default="last",
            help="Which page(s) to stamp",
        )
        parser.add_argument("--width", type=float, default=150.0)
        parser.add_argument("--margin-right", type=float, default=50.0)
        parser.add_argument("--margin-bottom", type=float, default=50.0)

    def handle(self, *args, **options):
        signature = getattr(settings, "SIGNATURE_IMAGE_PATH", "")
        if not signature or not os.path.isfile(signature):
            raise CommandError(
                "Signature image missing. Place it at: {}".format(signature)
            )

        pdfs = []
        for item in options["inputs"]:
            if os.path.isdir(item):
                pdfs.extend(sorted(glob.glob(os.path.join(item, "*.pdf"))))
                pdfs.extend(sorted(glob.glob(os.path.join(item, "*.PDF"))))
            elif os.path.isfile(item) and item.lower().endswith(".pdf"):
                pdfs.append(item)
            else:
                self.stderr.write("Skipping (not a PDF/folder): {}".format(item))

        # unique preserve order
        seen = set()
        unique = []
        for p in pdfs:
            key = os.path.abspath(p)
            if key not in seen:
                seen.add(key)
                unique.append(p)

        if not unique:
            raise CommandError("No PDF files found.")

        out_dir = options["output"] or os.path.join(settings.MEDIA_ROOT, "output")
        page = options["page"]
        page_index = {"last": -1, "first": 0, "all": None}[page]

        results = stamp_many(
            unique,
            signature,
            out_dir,
            page_index=page_index,
            signature_width=options["width"],
            margin_right=options["margin_right"],
            margin_bottom=options["margin_bottom"],
        )
        self.stdout.write(self.style.SUCCESS("Signed {} PDF(s):".format(len(results))))
        for path in results:
            self.stdout.write("  " + path)
