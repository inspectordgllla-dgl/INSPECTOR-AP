# நூலக பணி - உத்தேச மாத பயணத் திட்டம் (Library Tour Planner)

இது ஒரு Flask வலை பயன்பாடு. இது Google Sheet-ல் உள்ள நூலகங்கள் பட்டியல் மற்றும்
அரசு விடுமுறை நாட்கள் தரவைப் பயன்படுத்தி, ஒவ்வொரு மாதத்திற்குமான உத்தேச பயணத்
திட்டத்தை (Date / Day / Place of duty) உருவாக்கத் தருகிறது.

## 1. Google Sheet அமைப்பு

Sheet ID: `1R0h8KZLz3fKsEYEb4PHDNwzQGD75Lc7qVrFk4I_aDy4`

- **Sheet1** : A நெடுவரிசை = நூலக வகை, B நெடுவரிசை = நூலகம் பெயர் (A2:B175)
- **HOLIDAYS** : DATE (dd/mm/yyyy), Holiday Name, Holiday day

⚠️ **முக்கியம்:** இந்த Sheet-ஐ Google Drive-ல் திறந்து,
`Share` → `General access` → **"Anyone with the link" → "Viewer"** என மாற்ற வேண்டும்.
இல்லையெனில் இணையதளம் தரவை படிக்க முடியாது.

## 2. உள்ளூரில் இயக்குதல் (Local run)

```bash
pip install -r requirements.txt
python app.py
```

பிறகு browser-ல் `http://localhost:5000` திற்க்கவும்.

## 3. GitHub-ல் பதிவேற்றுதல்

```bash
git init
git add .
git commit -m "Library tour planner - initial version"
git branch -M main
git remote add origin https://github.com/<உங்கள்-username>/library-tour-planner.git
git push -u origin main
```

## 4. Render-ல் Deploy செய்தல்

1. https://render.com -ல் உள்நுழையவும் (GitHub கணக்கு மூலம் உள்நுழையலாம்).
2. **New +** → **Web Service** என தேர்ந்தெடுக்கவும்.
3. நீங்கள் push செய்த GitHub repository-ஐ இணைக்கவும்.
4. அமைப்புகள்:
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
5. (விருப்பப்படி) Environment Variables பகுதியில் `SHEET_ID`,
   `LIBRARY_SHEET_NAME`, `HOLIDAY_SHEET_NAME` ஆகியவற்றை தேவைப்பட்டால் மாற்றலாம்
   (repo-வில் `render.yaml` இருப்பதால் Render அதை தானாகவே கண்டறியும் - "Apply
   render.yaml" option-ஐ தேர்ந்தெடுக்கலாம்).
6. **Create Web Service** அழுத்தவும். சில நிமிடங்களில் இணையதளம் தயாராகிவிடும்.

## 5. பயன்பாடு

- இணையதளத்தை திறந்தவுடன், **இந்த மாதத்திற்கான** நாட்காட்டி தானாகவே தோன்றும்
  (மேலே உள்ள Year/Month dropdown மூலம் வேறு மாதத்தையும் தேர்ந்தெடுக்கலாம்).
- ஒவ்வொரு தேதிக்கும் "பணியிடம்" dropdown-ல் மூன்றில் ஒன்றைத் தேர்ந்தெடுக்கவும்:
  1. நூலகங்கள் பார்வை
  2. அலுவலகப் பணி
  3. நூலகங்கள் ஆய்வு
- "நூலகங்கள் பார்வை" / "நூலகங்கள் ஆய்வு" தேர்ந்தெடுக்கும்போது நூலகம் பெயர்
  dropdown தானாக இயக்கப்படும். "நூலகங்கள் ஆய்வு" தேர்ந்தெடுத்தால் கூடுதலாக
  ஆண்டு (2024-2025 / 2025-2026 / 2027-2028) dropdown-ம் தோன்றும்.
- அரசு விடுமுறை நாட்கள் **சிவப்பு நிறத்திலும்**, ஞாயிற்றுக்கிழமைகள் **மஞ்சள்
  நிறத்திலும்** காட்டப்படும்.
- கீழே உள்ள "பயணத் திட்டம் தயார் செய்" பொத்தானை அழுத்தினால், இறுதி பயணத் திட்ட
  அட்டவணை (நாள் / கிழமை / பணியிடம்) தயாராகும் - அதை அச்சிடலாம் (Print/PDF) அல்லது
  CSV ஆக பதிவிறக்கம் செய்யலாம்.

## 6. அடுத்த கட்டம் (பின்னர் சேர்க்கலாம்)

- அறிக்கைகள் (reports) பகுதி - இதுவரை தயார் செய்யப்பட்ட பயணத் திட்டங்களை
  சேமித்து, மாத/ஆண்டு வாரியாக பட்டியலிட.
- நிரந்தர சேமிப்பு (database) - தற்போது ஒவ்வொரு முறையும் புதிதாக உருவாக்கப்படுகிறது,
  சேமிக்கப்படவில்லை.
