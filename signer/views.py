import json
import os

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms import SetupForm, copy_file, new_job_dir, save_upload
from .pdf_signer import (
    get_pdf_page_info,
    list_pdfs_in_path,
    stamp_many_with_placements,
)


def _job_from_session(request):
    job = request.session.get("sign_job")
    if not job:
        return None
    root = job.get("job_dir")
    if not root or not os.path.isdir(root):
        return None
    return job


@require_http_methods(["GET", "POST"])
def home(request):
    """Step 1: signature, sample PDF, input path, output path."""
    form = SetupForm()
    if request.method == "POST":
        form = SetupForm(request.POST, request.FILES)
        if form.is_valid():
            job_id, job_dir = new_job_dir()
            data = form.cleaned_data

            # Signature
            if data.get("signature"):
                sig_name = data["signature"].name or "signature.png"
                ext = os.path.splitext(sig_name)[1] or ".png"
                sig_path = save_upload(
                    data["signature"], os.path.join(job_dir, "signature" + ext)
                )
            else:
                src = data["signature_path"]
                ext = os.path.splitext(src)[1] or ".png"
                sig_path = copy_file(src, os.path.join(job_dir, "signature" + ext))

            # Resolve PDFs to sign + sample for preview
            input_path = data.get("input_path") or ""
            pdfs_to_sign = list_pdfs_in_path(input_path) if input_path else []

            sample_path = os.path.join(job_dir, "sample.pdf")
            sample_original_name = None
            if data.get("sample_pdf"):
                sample_original_name = os.path.basename(
                    data["sample_pdf"].name or "document.pdf"
                )
                if not sample_original_name.lower().endswith(".pdf"):
                    sample_original_name = sample_original_name + ".pdf"
                save_upload(data["sample_pdf"], sample_path)
            elif pdfs_to_sign:
                sample_original_name = os.path.basename(pdfs_to_sign[0])
                copy_file(pdfs_to_sign[0], sample_path)
            else:
                sample_path = None

            # Extra uploaded PDFs (N files)
            uploads_dir = os.path.join(job_dir, "uploads")
            os.makedirs(uploads_dir, exist_ok=True)
            for uploaded in request.FILES.getlist("extra_pdfs"):
                name = uploaded.name or "document.pdf"
                if not name.lower().endswith(".pdf"):
                    continue
                dest = os.path.join(uploads_dir, os.path.basename(name))
                save_upload(uploaded, dest)
                pdfs_to_sign.append(dest)
                if sample_path is None:
                    sample_path = os.path.join(job_dir, "sample.pdf")
                    sample_original_name = os.path.basename(name)
                    copy_file(dest, sample_path)

            if sample_path is None:
                messages.error(request, "Could not resolve a sample PDF.")
                return render(request, "signer/setup.html", {"form": form, "step": 1})

            if not pdfs_to_sign:
                # Only the uploaded sample will be signed — keep original filename
                only = os.path.join(
                    uploads_dir, sample_original_name or "document.pdf"
                )
                copy_file(sample_path, only)
                pdfs_to_sign = [only]

            try:
                pages = get_pdf_page_info(sample_path)
            except Exception as exc:
                messages.error(request, "Could not read PDF: {}".format(exc))
                return render(request, "signer/setup.html", {"form": form, "step": 1})

            if not pages:
                messages.error(request, "PDF has no pages.")
                return render(request, "signer/setup.html", {"form": form, "step": 1})

            output_path = data["output_path"]
            try:
                os.makedirs(output_path, exist_ok=True)
            except OSError as exc:
                messages.error(request, "Cannot create output folder: {}".format(exc))
                return render(request, "signer/setup.html", {"form": form, "step": 1})

            request.session["sign_job"] = {
                "job_id": job_id,
                "job_dir": job_dir,
                "signature_path": sig_path,
                "sample_path": sample_path,
                "sample_url": settings.MEDIA_URL
                + "jobs/{}/sample.pdf".format(job_id),
                "signature_url": settings.MEDIA_URL
                + "jobs/{}/{}".format(job_id, os.path.basename(sig_path)),
                "pdfs_to_sign": pdfs_to_sign,
                "output_path": output_path,
                "pages": pages,
            }
            return redirect("positions")

    return render(request, "signer/setup.html", {"form": form, "step": 1})


@require_http_methods(["GET", "POST"])
def positions(request):
    """Step 2: set signature position per page (click preview or type X/Y)."""
    job = _job_from_session(request)
    if not job:
        messages.warning(request, "Start by uploading a PDF and signature.")
        return redirect("home")

    pages = job["pages"]
    if request.method == "POST":
        placements = []
        for i in range(len(pages)):
            enabled = request.POST.get("enabled_{}".format(i)) == "on"
            try:
                x = float(request.POST.get("x_{}".format(i), "0") or 0)
                y = float(request.POST.get("y_{}".format(i), "0") or 0)
                width = float(request.POST.get("width_{}".format(i), "150") or 150)
            except ValueError:
                messages.error(request, "Invalid number on page {}.".format(i + 1))
                return redirect("positions")
            placements.append(
                {
                    "page": i,
                    "enabled": enabled,
                    "x": x,
                    "y": y,
                    "width": width,
                }
            )

        if not any(p["enabled"] for p in placements):
            messages.error(request, "Enable at least one page for signing.")
            return redirect("positions")

        try:
            results = stamp_many_with_placements(
                job["pdfs_to_sign"],
                job["signature_path"],
                job["output_path"],
                placements,
            )
        except Exception as exc:
            messages.error(request, "Signing failed: {}".format(exc))
            return redirect("positions")

        from .s3_upload import upload_files

        # Copy signed files to S3 in the background (no S3 UI)
        try:
            upload_files(results)
        except Exception:
            pass

        request.session.pop("sign_job", None)
        return render(
            request,
            "signer/done.html",
            {
                "step": 3,
                "results": results,
                "output_path": job["output_path"],
                "count": len(results),
            },
        )

    # Defaults: bottom-right, enabled on last page only
    defaults = []
    for i, page in enumerate(pages):
        width = 150.0
        defaults.append(
            {
                "index": i,
                "label": "Page {}".format(i + 1),
                "width_pt": page["width"],
                "height_pt": page["height"],
                "enabled": i == len(pages) - 1,
                "x": max(0.0, page["width"] - width - 50),
                "y": 50.0,
                "sig_width": width,
            }
        )

    return render(
        request,
        "signer/positions.html",
        {
            "step": 2,
            "job": job,
            "defaults": defaults,
            "defaults_json": json.dumps(defaults),
            "pages_json": json.dumps(pages),
        },
    )


@require_http_methods(["GET"])
def reset_job(request):
    request.session.pop("sign_job", None)
    return redirect("home")
