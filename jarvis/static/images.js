/* Picture helpers shared by the computer and phone apps.
 * Photos are shrunk in the browser before upload (phone photos can be 5-10 MB; models
 * don't need that much detail), and stored images are shown via authenticated requests. */
(function (root) {
  "use strict";

  const MAX_SIDE = 1600;

  async function toDataUrl(file, maxSide) {
    maxSide = maxSide || MAX_SIDE;
    if (!file || !/^image\//.test(file.type || "")) throw new Error("That file isn't a picture.");
    let bitmap = null;
    try {
      bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    } catch (_) {
      bitmap = null; // e.g. HEIC on browsers that can't decode it
    }
    if (!bitmap) {
      if (file.size > 8 * 1024 * 1024) throw new Error("This picture format can't be read here. Try a JPEG or PNG.");
      return await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(new Error("The picture could not be read."));
        reader.readAsDataURL(file);
      });
    }
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#fff"; // transparent PNGs become readable on white
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    if (bitmap.close) bitmap.close();
    return canvas.toDataURL("image/jpeg", 0.86);
  }

  const cache = new Map();
  /* Stored images need the same login header as other requests, so fetch them as blobs. */
  async function objectUrl(name, headers) {
    if (cache.has(name)) return cache.get(name);
    const res = await fetch("/api/images/" + encodeURIComponent(name), { headers: headers || {} });
    if (!res.ok) throw new Error("Image not available");
    const url = URL.createObjectURL(await res.blob());
    cache.set(name, url);
    return url;
  }

  function thumb(src, alt) {
    const img = document.createElement("img");
    img.className = "thumb";
    img.alt = alt || "Attached picture";
    img.src = src;
    return img;
  }

  root.JarvisImages = { toDataUrl, objectUrl, thumb };
})(this);
