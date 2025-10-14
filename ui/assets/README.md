# UI Assets

This folder contains all visual assets for the Argusa Data Challenge website and emails.

## 📁 Directory Structure

```
ui/assets/
├── images/
│   ├── argusa-square.png       # Square logo for email headers
│   ├── argusa-horizontal.png   # Horizontal logo for website header (optional)
│   └── favicon.ico             # Website favicon (optional)
├── css/                        # Custom stylesheets (if needed)
└── README.md                   # This file
```

## 🖼️ Logo Files

### argusa-square.png
- **Usage**: Email confirmation headers
- **Recommended size**: 400x400px to 600x600px
- **Format**: PNG with transparent background
- **File size**: < 100KB for fast email loading

### argusa-horizontal.png (optional)
- **Usage**: Website header
- **Recommended size**: 800x200px (or similar aspect ratio)
- **Format**: PNG with transparent background

### favicon.ico (optional)
- **Usage**: Browser tab icon
- **Size**: 32x32px or 64x64px
- **Format**: ICO or PNG

## 🎨 Brand Colors

Argusa color palette (from argusa-charte_couleure-fontes):

| Color  | Hex Code  | Usage                    |
|--------|-----------|--------------------------|
| Blue   | `#004B87` | Primary, headers, links  |
| Yellow | `#FDB913` | Accent, highlights       |
| Black  | `#000000` | Text, contrast           |
| Red    | `#E94E1B` | Accent, CTAs             |

## 📧 Email Logo Setup

### Step 1: Add Logo to This Folder

Copy your logo file here:
```bash
cp ~/path/to/argusa-square.png ui/assets/images/argusa-square.png
```

### Step 2: Host Logo Publicly

**Option A: Use GitHub (Recommended)**

1. Commit and push the logo:
   ```bash
   git add ui/assets/images/argusa-square.png
   git commit -m "Add Argusa logo"
   git push
   ```

2. Get the raw GitHub URL:
   ```
   https://raw.githubusercontent.com/YOUR-ORG/ecoflex_eval_pipeline/main/ui/assets/images/argusa-square.png
   ```

**Option B: Serve from Your Server**

1. Copy to server:
   ```bash
   scp ui/assets/images/argusa-square.png ubuntu@your-server:/var/www/html/assets/
   ```

2. Configure Nginx to serve static files (if not already done)

3. Use URL:
   ```
   https://your-domain.com/assets/argusa-square.png
   ```

### Step 3: Configure Email

Add to `/etc/ecoflex.env` on the server:

```bash
EMAIL_LOGO_URL=https://raw.githubusercontent.com/YOUR-ORG/ecoflex_eval_pipeline/main/ui/assets/images/argusa-square.png
```

Or if serving from your own server:
```bash
EMAIL_LOGO_URL=https://your-domain.com/assets/argusa-square.png
```

### Step 4: Restart Service

```bash
sudo systemctl restart ecoflex
```

### Step 5: Test

Send a test submission and check the email!

## 🌐 Website Logo Setup

### Update index.html

Edit `ui/index.html` to add the logo:

```html
<div class="header">
    <img src="assets/images/argusa-horizontal.png" alt="Argusa" class="logo">
    <h1>Argusa Data Challenge</h1>
</div>
```

Add CSS:
```css
.header .logo {
    max-width: 300px;
    height: auto;
    margin-bottom: 20px;
}
```

## 📝 Logo Requirements

### For Emails
- **Format**: PNG with transparent background
- **Size**: 400-600px wide/tall (square or horizontal)
- **File size**: < 100KB (compress if needed)
- **Background**: Transparent (PNG) or white

### For Website
- **Format**: PNG or SVG
- **Size**: Any (will be scaled with CSS)
- **Optimization**: Use tools like TinyPNG or ImageOptim

## 🔧 Logo Optimization

### Compress PNG Files

**Online tools:**
- https://tinypng.com/
- https://compressor.io/

**Command line (macOS/Linux):**
```bash
# Install pngquant
brew install pngquant  # macOS
# or
apt-get install pngquant  # Ubuntu

# Compress
pngquant --quality=65-80 argusa-square.png -o argusa-square-optimized.png
```

### Convert to Different Formats

```bash
# PNG to ICO (favicon)
convert argusa-square.png -resize 32x32 favicon.ico

# PNG to WebP (modern format)
cwebp -q 80 argusa-square.png -o argusa-square.webp
```

## 🚀 Quick Setup Commands

```bash
# 1. Add your logo to this folder
cp ~/Downloads/argusa-square.png ui/assets/images/

# 2. Optimize it (optional)
pngquant --quality=65-80 ui/assets/images/argusa-square.png

# 3. Commit to git
git add ui/assets/
git commit -m "Add Argusa logo and assets"
git push

# 4. Get GitHub raw URL
echo "https://raw.githubusercontent.com/$(git remote get-url origin | sed 's/.*github.com[:/]//;s/.git$//')/main/ui/assets/images/argusa-square.png"

# 5. Add to server config
ssh ubuntu@your-server
sudo nano /etc/ecoflex.env
# Add: EMAIL_LOGO_URL=https://...
sudo systemctl restart ecoflex
```

## 📚 Additional Resources

- [Email-Safe Images Guide](https://www.campaignmonitor.com/blog/email-marketing/correct-image-sizes-for-email/)
- [PNG Optimization](https://tinypng.com/)
- [Favicon Generator](https://realfavicongenerator.net/)

---

**Note**: Make sure to test the logo in different email clients (Gmail, Outlook, Apple Mail) to ensure it displays correctly!

