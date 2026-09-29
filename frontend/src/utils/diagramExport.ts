export function downloadDiagramSvg(svgContent: string, prefix: string): void {
  const blob = new Blob([svgContent], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${prefix}-${Date.now()}.svg`;
  link.click();
  URL.revokeObjectURL(url);
}

export function downloadDiagramPng(
  svgContent: string,
  prefix: string,
  svgElement?: SVGSVGElement | null,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const serialized = svgElement ? new XMLSerializer().serializeToString(svgElement) : svgContent;
    const source = serialized.includes("xmlns=")
      ? serialized
      : serialized.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
    const blob = new Blob([source], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, image.naturalWidth);
      canvas.height = Math.max(1, image.naturalHeight);
      const context = canvas.getContext("2d");
      if (!context) {
        URL.revokeObjectURL(url);
        reject(new Error("PNG 캔버스를 만들 수 없습니다."));
        return;
      }
      context.drawImage(image, 0, 0);
      URL.revokeObjectURL(url);
      canvas.toBlob((pngBlob) => {
        if (!pngBlob) {
          reject(new Error("PNG 변환에 실패했습니다."));
          return;
        }
        const pngUrl = URL.createObjectURL(pngBlob);
        const link = document.createElement("a");
        link.href = pngUrl;
        link.download = `${prefix}-${Date.now()}.png`;
        link.click();
        URL.revokeObjectURL(pngUrl);
        resolve();
      }, "image/png");
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("SVG를 이미지로 불러오지 못했습니다."));
    };
    image.src = url;
  });
}
