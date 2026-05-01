const Tesseract = require('tesseract.js');

function normalizeWord(word, index) {
    const bbox = word.bbox || {};
    const x0 = Number.isFinite(bbox.x0) ? bbox.x0 : bbox.left;
    const y0 = Number.isFinite(bbox.y0) ? bbox.y0 : bbox.top;
    const x1 = Number.isFinite(bbox.x1) ? bbox.x1 : (x0 + (bbox.width || 0));
    const y1 = Number.isFinite(bbox.y1) ? bbox.y1 : (y0 + (bbox.height || 0));

    return {
        text: String(word.text || '').trim(),
        left: Math.round(x0 || 0),
        top: Math.round(y0 || 0),
        width: Math.max(0, Math.round((x1 || 0) - (x0 || 0))),
        height: Math.max(0, Math.round((y1 || 0) - (y0 || 0))),
        conf: Number.isFinite(word.confidence) ? word.confidence : -1,
        index,
    };
}

async function doOCR(imagePath) {
    try {
        const { data } = await Tesseract.recognize(imagePath, 'eng', { logger: () => {} });
        const words = Array.isArray(data.words)
            ? data.words.map(normalizeWord).filter(word => word.text && word.width > 0 && word.height > 0)
            : [];

        console.log('RESULT_JSON_START');
        console.log(JSON.stringify({ text: data.text || '', words }));
        console.log('RESULT_JSON_END');
    } catch (error) {
        console.error('OCR_DATA_ERROR:', error.message);
        process.exit(1);
    }
}

const imagePath = process.argv[2];
if (imagePath) {
    doOCR(imagePath);
} else {
    console.error('No image path provided');
    process.exit(1);
}
