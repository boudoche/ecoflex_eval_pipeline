# Email Deliverability Guide

This guide helps you avoid emails ending up in spam folders.

## 🎯 What I Fixed in the Code

### 1. **Professional Email Headers**
- Added sender name: `"Ecoflex Hackathon <your-email@gmail.com>"`
- Added `Reply-To` header
- Added `X-Mailer` and priority headers
- Better subject line with checkmark emoji

### 2. **HTML + Plain Text Email**
- Now sends both HTML and plain text versions
- Professional styling with green theme
- Proper email structure
- Clear call-to-action

### 3. **Better Content**
- More detailed, professional message
- Clear submission details
- Proper footer with disclaimer
- No suspicious keywords

## 🔧 Server Configuration

### Required Environment Variables

Add these to `/etc/ecoflex.env`:

```bash
# Basic SMTP (already configured)
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
SMTP_FROM=your-email@gmail.com

# NEW: Improve deliverability
SMTP_FROM_NAME="Ecoflex Hackathon"
SMTP_REPLY_TO=your-email@gmail.com
```

### Restart the Service

```bash
sudo systemctl restart ecoflex
```

## 📧 Gmail-Specific Configuration

### 1. **Use a Professional Gmail Account**

✅ **Good**: `ecoflex.hackathon@gmail.com`
❌ **Bad**: `random123xyz@gmail.com`

### 2. **Set Up App Password** (Already Done)

You should already have this configured.

### 3. **Enable "Less Secure App Access" (If Needed)**

Go to: https://myaccount.google.com/lesssecureapps
- Turn ON "Allow less secure apps"
- Note: This is only needed if app passwords don't work

### 4. **Warm Up Your Email Account**

If this is a new Gmail account:
- Send a few manual emails first
- Wait 24-48 hours before sending bulk emails
- Start with small volumes (5-10 emails/day)
- Gradually increase volume

### 5. **Add Recipients to Contacts**

Have participants add your email to their contacts:
- This significantly improves deliverability
- Ask them to do this before the hackathon

## 🛡️ DNS Configuration (Advanced)

For best deliverability, configure these DNS records for your domain:

### SPF Record

Add a TXT record to your domain:

```
Type: TXT
Name: @
Value: v=spf1 include:_spf.google.com ~all
```

### DKIM (Domain Keys)

1. Go to Gmail Admin Console
2. Navigate to Apps > Google Workspace > Gmail > Authenticate email
3. Generate DKIM key
4. Add the provided TXT record to your DNS

### DMARC Record

Add a TXT record:

```
Type: TXT
Name: _dmarc
Value: v=DMARC1; p=none; rua=mailto:your-email@gmail.com
```

**Note**: DNS configuration only works if you're sending from your own domain (e.g., `@ecoflex.com`), not from Gmail.

## ✅ Best Practices

### 1. **Content Guidelines**

✅ **Do**:
- Use clear, professional language
- Include unsubscribe/disclaimer text
- Use proper HTML structure
- Include both text and HTML versions
- Use a clear subject line

❌ **Avoid**:
- ALL CAPS text
- Excessive exclamation marks!!!
- Spam trigger words (FREE, URGENT, ACT NOW)
- Too many links
- Large images
- Suspicious attachments

### 2. **Sending Practices**

✅ **Do**:
- Send from a consistent email address
- Use a professional sender name
- Send at reasonable times (9 AM - 5 PM)
- Limit sending rate (max 100-200/hour for Gmail)
- Monitor bounce rates

❌ **Avoid**:
- Sending to invalid addresses
- Sending too many emails at once
- Changing sender address frequently
- Sending at odd hours (2 AM)

### 3. **Recipient Management**

✅ **Do**:
- Verify email addresses before sending
- Remove bounced addresses
- Respect opt-outs
- Use double opt-in for mailing lists

## 🧪 Testing Email Deliverability

### 1. **Test with Mail-Tester**

```bash
# Send a test email to the address provided by mail-tester.com
curl -X POST http://your-server/grade \
  -H "Content-Type: application/json" \
  -H "X-Submission-Token: your-token" \
  -d @test_submission.json
```

Then check the score at: https://www.mail-tester.com/

**Target**: Score 8/10 or higher

### 2. **Test with Different Providers**

Send test emails to:
- Gmail
- Outlook/Hotmail
- Yahoo Mail
- ProtonMail

Check if they land in inbox or spam.

### 3. **Check Email Headers**

Have a recipient forward the email and check headers for:
- SPF: PASS
- DKIM: PASS
- DMARC: PASS

## 🚨 Troubleshooting

### Emails Still Going to Spam?

#### 1. **Check Gmail Sending Limits**

Gmail limits:
- **Free Gmail**: 500 emails/day
- **Google Workspace**: 2,000 emails/day

If you exceed these, emails will be delayed or blocked.

#### 2. **Check for Blacklisting**

Check if your IP is blacklisted:
- https://mxtoolbox.com/blacklists.aspx
- Enter your server's IP address

If blacklisted, contact the blacklist provider to request removal.

#### 3. **Use a Dedicated Email Service**

For better deliverability, consider using:
- **SendGrid** (Free tier: 100 emails/day)
- **Mailgun** (Free tier: 5,000 emails/month)
- **Amazon SES** (Very cheap, high deliverability)

These services have better reputation and deliverability.

### Using SendGrid (Recommended)

1. **Sign up**: https://sendgrid.com/
2. **Get API key**
3. **Update `/etc/ecoflex.env`**:

```bash
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASS=your-sendgrid-api-key
SMTP_FROM=your-verified-email@domain.com
SMTP_FROM_NAME="Ecoflex Hackathon"
```

4. **Restart service**: `sudo systemctl restart ecoflex`

## 📊 Monitoring

### Check Email Logs

```bash
# View email sending logs
sudo journalctl -u ecoflex -f | grep "email"

# Check for errors
sudo journalctl -u ecoflex | grep "Failed to send"
```

### Monitor Delivery Rates

Track:
- **Sent**: Total emails sent
- **Delivered**: Emails that reached inbox
- **Bounced**: Invalid addresses
- **Spam**: Marked as spam

## 🎯 Quick Fixes Checklist

- [x] Updated email code with HTML + plain text
- [ ] Set `SMTP_FROM_NAME` in `/etc/ecoflex.env`
- [ ] Set `SMTP_REPLY_TO` in `/etc/ecoflex.env`
- [ ] Restart ecoflex service
- [ ] Test with mail-tester.com
- [ ] Ask participants to add email to contacts
- [ ] Warm up email account (if new)
- [ ] Consider using SendGrid/Mailgun
- [ ] Monitor delivery rates

## 💡 Additional Tips

1. **Pre-announce**: Send a test email to all participants before the hackathon
2. **Whitelist**: Ask participants to whitelist your email address
3. **Alternative**: Provide a web dashboard where participants can check results
4. **Backup**: Have a secondary notification method (Slack, Discord, etc.)

## 🔗 Useful Resources

- [Gmail SMTP Settings](https://support.google.com/mail/answer/7126229)
- [Email Deliverability Best Practices](https://sendgrid.com/blog/email-deliverability-best-practices/)
- [SPF/DKIM/DMARC Guide](https://www.cloudflare.com/learning/dns/dns-records/dns-spf-record/)
- [Mail Tester](https://www.mail-tester.com/)
- [MX Toolbox](https://mxtoolbox.com/)

---

**Need Help?** Check the server logs or test with mail-tester.com to diagnose issues.

