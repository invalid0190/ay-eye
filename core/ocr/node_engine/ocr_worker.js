const Tesseract = require('tesseract.js');
const path = require('path');

async function doOCR(imagePath) {
    try {
        const { data: { text } } = await Tesseract.recognize(imagePath, 'eng', { logger: m => {} });
        console.log("RESULT_START");
        console.log(text);
        console.log("RESULT_END");
    } catch (error) {
        console.error("OCR_ERROR:", error.message);
        process.exit(1);
    }
}

const imagePath = process.argv[2];
if (imagePath) {
    doOCR(imagePath);
} else {
    console.error("No image path provided");
    process.exit(1);
}
