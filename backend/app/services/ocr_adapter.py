from __future__ import annotations

from pathlib import Path


class OcrAdapter:
    def extract_text(self, image_path: Path) -> str:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Local OCR engine is not installed. Install rapidocr-onnxruntime to enable receipt OCR."
            ) from exc

        ocr = RapidOCR()
        result, _ = ocr(str(image_path))
        if not result:
            return ""
        lines: list[str] = []
        for item in result:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                lines.append(str(item[1]))
        return "\n".join(line.strip() for line in lines if line).strip()
