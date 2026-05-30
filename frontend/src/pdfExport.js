// Генерация PDF целиком на фронтенде (frontend-only, без сервера).
// Клонируем бланк акта в off-screen контейнер фиксированной ширины и снимаем
// его html2canvas — так PDF не зависит от размера/масштаба экрана,
// кириллица рендерится корректно, внешний вид бланка сохраняется.

const CAPTURE_W = 1120;

export async function exportNodeToPdf(node, filename = "akt.pdf") {
  const jsPDFCtor = window.jspdf?.jsPDF;
  const html2canvas = window.html2canvas;

  // Фолбэк, если CDN-библиотеки не загрузились (нет интернета):
  // открываем системный диалог печати → «Сохранить как PDF».
  if (!jsPDFCtor || !html2canvas) {
    printFallback(node);
    return { fallback: true };
  }

  // Клон акта вне экрана, на полной ширине — без сжатия и трансформаций.
  const holder = document.createElement("div");
  holder.style.cssText =
    "position:fixed;left:-12000px;top:0;width:" + CAPTURE_W + "px;background:#fff;z-index:-1;";
  const clone = node.cloneNode(true);
  clone.style.width = CAPTURE_W + "px";
  clone.style.maxWidth = "none";
  clone.style.boxShadow = "none";
  clone.style.border = "none";
  holder.appendChild(clone);
  document.body.appendChild(holder);

  let canvas;
  try {
    await new Promise((r) => setTimeout(r, 60)); // дать браузеру разложить вёрстку
    canvas = await html2canvas(clone, {
      scale: 2,
      backgroundColor: "#ffffff",
      useCORS: true,
      logging: false,
      width: CAPTURE_W,
      windowWidth: CAPTURE_W + 80,
    });
  } finally {
    document.body.removeChild(holder);
  }

  const img = canvas.toDataURL("image/jpeg", 0.96);
  // Альбомная (горизонтальная) ориентация — широкая таблица помещается целиком.
  const pdf = new jsPDFCtor({ unit: "mm", format: "a4", orientation: "landscape" });
  const pageW = pdf.internal.pageSize.getWidth();
  const pageH = pdf.internal.pageSize.getHeight();
  const margin = 8;
  const maxW = pageW - margin * 2;
  const maxH = pageH - margin * 2;

  const ratio = canvas.height / canvas.width;
  let imgW = maxW;
  let imgH = imgW * ratio;
  if (imgH > maxH) {
    imgH = maxH;
    imgW = imgH / ratio;
  }
  const x = (pageW - imgW) / 2;
  const y = (pageH - imgH) / 2;
  pdf.addImage(img, "JPEG", x, y, imgW, imgH);
  pdf.save(filename);
  return { fallback: false };
}

function printFallback(node) {
  const w = window.open("", "_blank");
  if (!w) return;
  w.document.write(
    `<html><head><title>Акт о приёмке запасов</title></head><body>${node.outerHTML}</body></html>`
  );
  w.document.close();
  w.focus();
  setTimeout(() => w.print(), 300);
}
