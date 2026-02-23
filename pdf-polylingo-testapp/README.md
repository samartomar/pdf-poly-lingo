# PDF Poly Lingo Test App

React test app for the PDF Poly Lingo translation service.

## Setup

1. **Install dependencies**
   ```bash
   npm install
   ```

2. **Configure API endpoint**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set `VITE_API_ENDPOINT` to your API Gateway URL (from TranslationService stack output).

   Get it with:
   ```bash
   aws cloudformation describe-stacks --stack-name Prod-TranslationService --region us-west-2 --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" --output text
   ```
   Or for direct deploy: replace `Prod-TranslationService` with `TranslationService`.

3. **Run dev server**
   ```bash
   npm run dev
   ```

4. Open http://localhost:5173 and:
   - Select a TXT, HTML, or PDF file (max 5MB)
   - Preview displays for PDF/HTML
   - Choose target language
   - Click **Translate**
   - Progress bar shows upload and translation status
   - Translated document loads in the page when ready; you can also download it.
