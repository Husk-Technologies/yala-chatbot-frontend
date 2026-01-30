# Yala WhatsApp Chatbot – Conversation Flow (Phase 1)

## Overview
Yala is a WhatsApp-based chatbot that provides funeral/event information to guests.
Users access the bot by scanning a QR code or messaging the WhatsApp number directly.

The bot is **menu-driven**, **low-friction**, and **respectful**, designed for all age groups.

---

## Entry Point

### Trigger
- User scans QR code **OR**
- User sends any message (e.g. "Hi") to the Yala WhatsApp number

---

## Step 1: Event Code Collection

**Bot Message:**
> Hello 👋  
> Welcome to Yala.  
> Please enter the **Event Code** on your card to continue.

**User Input:**
- Text (event code)

**System Action:**
- Validate event code via backend API

**If invalid:**
> Sorry, that event code was not found.  
> Please check the card and try again.

**Loop:** Remain in Step 1 until valid code is provided.

---

## Step 2: Event Confirmation & Welcome

**Bot Message (after valid code):**
> Thank you.  
> This is the funeral/event of **{Event Name}**.  
>  
> Please enter your **name** to continue.

**User Input:**
- Guest name (free text)

**System Action:**
- Store guest name in session context

---

## Step 3: Main Menu

**Bot Message:**
> Thank you, **{Guest Name}**.  
> How can we help you today?

**Menu Options:**
1. 📄 Download event brochure  
2. 💝 Give / Donate  
3. 🕊️ Send condolence / message  

**User Input:**
- Numeric selection (1, 2, or 3)

---

## Step 4A: Download Event Brochure

**System Action:**
- Fetch brochure file from backend
- Send brochure directly as a WhatsApp document (PDF/Image)

**Bot Message:**
> Here is the event brochure.  
> You may download it to your phone.

**After Completion:**
- Return to Main Menu

---

## Step 4B: Give / Donate

**Bot Message:**
> Thank you for your willingness to support.  
> Please follow the instructions below to complete your donation.

**System Action (Phase 1):**
- Trigger backend payment flow
- Provide payment instructions (MoMo / gateway)
- Listen for payment confirmation webhook

**On Success:**
> Thank you for your donation.  
> Your support is appreciated by the family.

**On Failure:**
> We couldn’t complete the donation.  
> Please try again later.

**After Completion:**
- Return to Main Menu

---

## Step 4C: Send Condolence / Message

**Bot Message:**
> Please type the message you would like to send to the family.

**User Input:**
- Free text condolence message

**System Action:**
- Store message in backend database
- Associate with event and guest

**Bot Message:**
> Thank you.  
> Your message has been sent to the family.

**After Completion:**
- Return to Main Menu

---

## Session Handling

- Maintain session using:
  - WhatsApp phone number
  - Event code
- Session expires after inactivity (e.g. 15–30 minutes)

---

## Error Handling

- Invalid inputs → gentle retry prompts
- Network issues → fallback apology message
- Backend errors → log and notify admin (silent to user)

---

## Design Principles

- Simple language
- Minimal steps
- Respectful tone
- WhatsApp-first (no external links unless required)

---

## Phase 1 Limitations

- No guest login or accounts
- No multi-event switching
- No analytics dashboard for guests
- No AI/free-form Q&A (future phase)

---

## End of Flow
