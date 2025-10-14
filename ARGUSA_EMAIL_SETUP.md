# Argusa Email Branding Setup

This guide explains how to add the Argusa logo to confirmation emails.

## 🎨 Email Design

The email now uses Argusa's brand colors:
- **Blue**: `#004B87` (primary)
- **Yellow**: `#FDB913`
- **Black**: `#000000`
- **Red**: `#E94E1B`

The email features:
- Diagonal striped header with all 4 brand colors
- Brand color bar separators
- Blue accents throughout
- Professional layout

## 📧 Adding the Argusa Logo

### Option 1: Host Logo Publicly (Recommended)

1. **Upload logo to a public location:**
   - GitHub repository (e.g., `https://raw.githubusercontent.com/your-org/repo/main/logo.png`)
   - Your website (e.g., `https://argusa.com/images/logo.png`)
   - Image hosting service (e.g., Imgur, Cloudinary)

2. **Add to server configuration:**

   Edit `/etc/ecoflex.env`:
   ```bash
   EMAIL_LOGO_URL=https://your-domain.com/path/to/argusa-logo.png
   ```

3. **Restart service:**
   ```bash
   sudo systemctl restart ecoflex
   ```

### Option 2: Embed Logo in Email (Alternative)

If you can't host the logo publicly, you can embed it as base64:

1. **Convert logo to base64:**
   ```bash
   base64 -i argusa-logo.png | tr -d '\n' > logo-base64.txt
   ```

2. **Update server.py** to use embedded image:
   ```python
   # In _send_confirmation_email function, replace logo_url line with:
   logo_base64 = os.getenv("EMAIL_LOGO_BASE64", "")
   logo_url = f"data:image/png;base64,{logo_base64}" if logo_base64 else ""
   ```

3. **Add to `/etc/ecoflex.env`:**
   ```bash
   EMAIL_LOGO_BASE64=iVBORw0KGgoAAAANSUhEUgAA... (your base64 string)
   ```

### Option 3: No Logo (Current Default)

If no logo URL is configured, the email will display without a logo but still use Argusa's brand colors.

## 🖼️ Logo Requirements

For best results:
- **Format**: PNG with transparent background
- **Size**: 400-600px wide (will be displayed at 200px)
- **Aspect ratio**: Horizontal logo works best
- **File size**: < 100KB for fast loading

## 🧪 Testing the Email

### 1. Test Locally

Create a test HTML file to preview:

```bash
cat > test-email.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; background-color: #ffffff; }
        .header { 
            background: linear-gradient(135deg, #004B87 0%, #004B87 25%, #FDB913 25%, #FDB913 50%, #000000 50%, #000000 75%, #E94E1B 75%, #E94E1B 100%);
            color: white; 
            padding: 30px 20px; 
            text-align: center; 
            border-radius: 5px 5px 0 0;
        }
        .logo { max-width: 200px; height: auto; margin-bottom: 15px; }
        .header h1 { margin: 0; font-size: 24px; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }
        .content { background-color: #f9f9f9; padding: 30px 20px; border: 1px solid #ddd; }
        .details { 
            background-color: white; 
            padding: 20px; 
            margin: 20px 0; 
            border-left: 5px solid #004B87;
            border-radius: 3px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .details h3 { color: #004B87; margin-top: 0; }
        .details ul { list-style: none; padding: 0; }
        .details li { padding: 8px 0; border-bottom: 1px solid #f0f0f0; }
        .details li:last-child { border-bottom: none; }
        .footer { 
            text-align: center; 
            margin-top: 20px; 
            padding: 20px;
            font-size: 12px; 
            color: #666;
            background-color: #f5f5f5;
            border-radius: 0 0 5px 5px;
        }
        .success { color: #004B87; font-weight: bold; font-size: 18px; }
        .brand-bar {
            height: 8px;
            background: linear-gradient(90deg, #004B87 0%, #004B87 25%, #FDB913 25%, #FDB913 50%, #000000 50%, #000000 75%, #E94E1B 75%, #E94E1B 100%);
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <img src="YOUR_LOGO_URL_HERE" alt="Argusa Logo" class="logo" />
            <h1>✓ Submission Received</h1>
        </div>
        <div class="brand-bar"></div>
        <div class="content">
            <p>Hello <strong>Team Name</strong>,</p>
            
            <p class="success">Your submission has been received successfully!</p>
            
            <div class="details">
                <h3>Submission Details</h3>
                <ul>
                    <li><strong>Team/Participant:</strong> Team Name</li>
                    <li><strong>Number of answers:</strong> 12</li>
                    <li><strong>Status:</strong> Received</li>
                </ul>
            </div>
            
            <p>Your submission file is attached to this email for your records.</p>
            
            <p>We will notify you once the evaluation is complete.</p>
            
            <p>Best regards,<br>
            <strong>The Argusa Data Challenge Team</strong></p>
        </div>
        <div class="footer">
            <div class="brand-bar" style="margin-bottom: 10px;"></div>
            <p>This is an automated message. Please do not reply to this email.</p>
        </div>
    </div>
</body>
</html>
EOF

# Open in browser
open test-email.html  # macOS
# or
xdg-open test-email.html  # Linux
```

### 2. Send Test Email

After configuring, send a test submission:

```bash
curl -X POST http://your-server/grade \
  -H "Content-Type: application/json" \
  -H "X-Submission-Token: your-test-token" \
  -d @test_submission.json
```

Check your email inbox for the branded confirmation.

## 📝 Environment Variables Summary

Add these to `/etc/ecoflex.env`:

```bash
# Email branding
SMTP_FROM_NAME="Argusa Data Challenge"
EMAIL_LOGO_URL=https://your-domain.com/path/to/logo.png

# Or use base64 (alternative)
# EMAIL_LOGO_BASE64=iVBORw0KGgoAAAANSUhEUgAA...
```

## 🎨 Color Reference

Argusa brand colors used in the email:

| Color  | Hex Code  | Usage                    |
|--------|-----------|--------------------------|
| Blue   | `#004B87` | Primary, headers, links  |
| Yellow | `#FDB913` | Accent, brand bars       |
| Black  | `#000000` | Text, brand bars         |
| Red    | `#E94E1B` | Accent, brand bars       |

## 🚀 Quick Setup Checklist

- [ ] Upload Argusa logo to public location
- [ ] Copy logo URL
- [ ] Add `EMAIL_LOGO_URL` to `/etc/ecoflex.env`
- [ ] Optionally customize `SMTP_FROM_NAME`
- [ ] Restart service: `sudo systemctl restart ecoflex`
- [ ] Send test submission
- [ ] Verify email looks correct
- [ ] Check spam folder if not received
- [ ] Ask recipient to add to contacts

## 💡 Tips

1. **Use a CDN** for faster logo loading
2. **Optimize logo** - compress to < 100KB
3. **Test on multiple email clients** (Gmail, Outlook, Apple Mail)
4. **Keep logo simple** - complex logos may not render well in all clients
5. **Use PNG** with transparent background for best results

## 🔍 Troubleshooting

### Logo not showing?

1. Check if URL is publicly accessible:
   ```bash
   curl -I https://your-logo-url.png
   ```
   Should return `200 OK`

2. Check email HTML source - logo URL should be present

3. Some email clients block external images by default
   - Gmail: "Display images" prompt
   - Outlook: "Download pictures" setting

### Colors not showing?

- Some email clients strip CSS
- The gradient backgrounds should work in most modern clients
- Plain text version will be used as fallback

### Email still looks plain?

- Check if HTML version is being sent
- View email source to see if HTML is present
- Some email clients prefer plain text by default

---

**Need help?** Check the main EMAIL_DELIVERABILITY.md guide or server logs.

