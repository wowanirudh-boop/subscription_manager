# Consumer subscription-tracking apps — research snapshot

> **Archived research, 6 September 2026.** Migrated from the [original shared ChatGPT conversation](https://chatgpt.com/share/6aeb0dfb-1c0c-83ec-b14d-b0ada3415cc6) into this repository. The analysis and confidence labels below are reproduced from that conversation; the citation markers have been replaced with durable links to the original primary sources. Product features, counts, availability, and policies were **not rechecked on migration** and may have changed since September.

---

Yes. I found a surprisingly active consumer subscription-tracking market, including **several products already using Gmail exactly the way you proposed**.

The important finding, though, is that the market looks **fragmented rather than won**: there is one large incumbent built around bank transactions, a large number of manual trackers, and a newer wave of small Gmail/email-first products.

**Overall confidence: High** — I used product websites, Google/Apple documentation, and official app-store listings rather than comparison blogs.

## 1. The landscape in one picture

| Product | How subscriptions are found | Prevent renewal surprises? | Relative maturity | How close to your idea? |
|---|---|---:|---|---:|
| **Rocket Money** | Bank/card transactions | ✅ | 🟢 Very large | 🟡 |
| **Hiatus** | Bank/financial accounts | ✅ | 🟢 Established | 🟡 |
| **Bobby** | Manual entry | ✅ | 🟡 Established niche | 🔴 |
| **BeforeItBills** | **Email inbox** | ✅ | 🟡 New/small | 🟢 **Very close** |
| **SubRadar** | **Gmail** | ✅ | 🟡 New/small | 🟢 **Very close** |
| **Substrack** | **Gmail** + manual | ✅ | 🔴 Very early | 🟢 **Very close** |
| **Subcut** | **Gmail + statements + Apple** | ✅ | 🔴 Very early | 🟢 **Very close** |
| **Spendloop** | **Gmail + notifications** | ✅ | 🔴 Early | 🟢 |
| **Subzero.money** | **Gmail** | ✅ | 🔴 Early web product | 🟢 **Very close** |
| **Subwise** 🇮🇳 | **Gmail → WhatsApp reminders** | ✅ | 🔴 Early | 🟢 **Extremely close** |

The most important distinction is **how they discover the subscription**.

---

# 2. The big incumbent: Rocket Money

### Rocket Money

This is probably the clearest proof that consumers care about the problem.

Rocket Money connects to bank accounts/cards and identifies recurring transactions automatically. It then shows subscriptions, upcoming bills, price changes and lets users cancel certain subscriptions. Its wider product includes budgeting, spending analysis and bill negotiation. (Sources: [Rocket Money on Google Play](https://play.google.com/store/apps/details/Truebill_Budget_Planner_Bill_Tracker_and_Reminder?hl=en_IN&id=com.truebill), [Rocket Money](https://www.rocketmoney.com/learn/personal-finance/tracking-expenses-with-rocket-money))

Its Google Play listing currently says **10M+ downloads and ~136K ratings/reviews**, making it in an entirely different scale category from most dedicated subscription apps. (Sources: [Rocket Money on Google Play](https://play.google.com/store/apps/details/Truebill_Budget_Planner_Bill_Tracker_and_Reminder?hl=en_IN&id=com.truebill))

### But there is an important limitation

Its fundamental data source is:

> **Bank transaction → detect recurring merchant**

rather than:

> **Email → understand subscription lifecycle**

And Rocket Money's financial connectivity is built around Plaid. Plaid's currently documented institution country codes cover the US, Canada, UK and a range of European markets — **India is not listed**. (Sources: [Plaid docs](https://plaid.com/docs/api/institutions/))

So Rocket Money proves demand very well, but it does **not necessarily solve an Indian/global Gmail-first use case well**.

**Confidence: High.**

---

# 3. The competitors you should pay the most attention to

These are much closer to the product you're considering.

## 🟠 BeforeItBills

This is one of the closest products I found.

The proposition is effectively:

**Connect email → detect subscriptions → warn before money leaves.**

It scans Gmail, Outlook, iCloud, Yahoo and IMAP email, extracts recurring charges and asks the user to confirm them. It says it recognizes **500+ services** and sends a warning **seven days before renewal**. No bank connection is required. (Sources: [BeforeItBills](https://www.beforeitbills.com/))

It also tracks:

- free trials
- monthly recurring spend
- upcoming payments
- 12-month forecast

Its App Store version launched in **June 2026**, and currently does not have enough ratings to show a ratings overview. (Sources: [BeforeItBills on App Store](https://apps.apple.com/be/app/beforeitbills/id6760515650))

So this appears to be **very new rather than an entrenched incumbent**.

**Similarity to your idea: ~9/10.**

**Confidence: High.**

---

## 🟠 SubRadar

Another direct competitor.

The app connects to Gmail and claims to identify:

- active subscriptions
- price
- billing cycle
- renewal date
- price changes

It then provides spending analysis and renewal reminders. (Sources: [SubRadar on App Store](https://apps.apple.com/in/app/subradar-subscription-manager/id6758894751))

The current App Store product launched on **March 26, 2026** and still doesn't have enough ratings for Apple to display an overall rating. (Sources: [SubRadar on App Store](https://apps.apple.com/in/app/subradar-subscription-manager/id6758894751))

That is an interesting signal: the idea exists, but this particular implementation does **not appear to have achieved mass adoption yet**.

**Similarity: ~9/10.**

**Confidence: High on functionality; Medium on adoption because App Store ratings are only a partial signal.**

---

## 🟠 Substrack

Android product.

It has a feature explicitly called **Gmail Auto-Detect**:

> connect Gmail → scan for subscription receipts → present detected subscriptions → add with one tap.

It tracks renewals, calendar, spending and multi-currency subscriptions. Gmail detection is part of its Pro tier. (Sources: [Substrack on Google Play](https://play.google.com/store/apps/details?id=com.kimekolab.substrack))

The striking part is scale: Google Play currently reports only **10+ downloads**. (Sources: [Substrack on Google Play](https://play.google.com/store/apps/details?id=com.kimekolab.substrack))

So this is essentially an extremely early competitor.

**Similarity: ~9/10.**

**Confidence: High.**

---

# 4. Subcut has an interesting alternative approach

Subcut is particularly worth studying from a product-design perspective.

Rather than relying on a single source, it supports:

**Gmail receipts + PDF/CSV bank statement + Apple subscriptions + manual entry**

and combines them into one subscription view. (Sources: [Subcut on App Store](https://apps.apple.com/in/app/subcut-subscription-tracker/id6758765733), [getsubcut.app](https://getsubcut.app/))

It then provides:

- renewal calendar
- free-trial warnings
- cancellation instructions
- monthly/yearly spend
- savings from cancelled subscriptions
- 800+ cancellation guides

That addresses an obvious weakness of Gmail-only discovery: **not every subscription will necessarily have an easily detectable email trail**.

But it is also tiny today. The Indian App Store currently shows only **2 ratings**. (Sources: [Subcut on App Store](https://apps.apple.com/in/app/subcut-subscription-tracker/id6758765733))

**Similarity: ~8/10.**

**Confidence: High.**

---

# 5. Spendloop

Spendloop is an Android subscription manager with Gmail discovery.

It can scan Gmail for receipts/invoices and also experiments with identifying subscriptions from Android notifications. It can detect things such as cancellation emails as well. (Sources: [Spendloop on Google Play](https://play.google.com/store/apps/details?hl=en-GB&id=com.spendloop.app), [Spendloop](https://spendloop.app/))

Its broader product includes:

- subscription calendar
- 90/180/365-day forecasts
- multiple currencies
- cards/payment methods
- shared subscriptions
- reminders

It was updated as recently as **August 12, 2026**, so it appears actively developed. (Sources: [Spendloop on Google Play](https://play.google.com/store/apps/details?hl=en-GB&id=com.spendloop.app))

**Similarity: ~8/10.**

**Confidence: High on features; Low–Medium on adoption because reliable scale data isn't available.**

---

# 6. Subzero.money

This is essentially your proposed UX in web form.

Its headline is literally:

> “Connect Gmail. We'll find every subscription linked to your inbox.”

It scans for:

- receipts
- renewals
- free trials
- price increases

and then deduplicates subscriptions and surfaces upcoming payments. (Sources: [Subzero](https://subzero.money/))

It also provides guided cancellation instructions.

They explicitly describe Gmail as their subscription discovery mechanism rather than requiring manual tracking.

The product appears relatively early and I could not find a reliable primary-source adoption number.

**Similarity: ~9/10.**

**Confidence: High on product functionality; Low on adoption.**

---

# 7. The one I think you should examine most carefully: Subwise 🇮🇳

This was the most interesting result given the problem you described.

Subwise is an **India-focused Gmail-based recurring-payment assistant**.

Its flow is:

**Connect Gmail → detect payments → organize recurring obligations → send WhatsApp reminders.**

It explicitly mentions examples such as:

- Netflix
- Spotify
- ChatGPT
- rent
- EMI
- insurance
- internet
- school fees
- credit-card payments

and displays amounts in ₹. (Sources: [Subwise](https://subwise.co.in/))

More importantly, its privacy documentation says it searches payment-related emails for things such as:

> receipts, invoices, renewals, **auto-pay/UPI mandates**, trials

and extracts merchant, amount, billing cycle, payment method and renewal/trial date. (Sources: [Subwise privacy policy](https://subwise.co.in/privacy))

It then sends reminders through WhatsApp rather than requiring the user to repeatedly open another finance application. (Sources: [Subwise](https://subwise.co.in/))

That is **very close to what you described**, with one conceptual expansion:

> subscriptions → recurring financial commitments.

### Subwise vs your original idea

Your concept:

**Gmail → find subscriptions → app → prevent forgotten renewal**

Subwise:

**Gmail → find recurring financial commitments → dashboard → WhatsApp reminder**

So I would treat them as a **direct competitor/reference product**, not an adjacent player.

I could not find trustworthy evidence that it has meaningful consumer scale yet.

**Similarity: ~9.5/10.**

**Confidence: High on product similarity; Low on adoption.**

---

# 8. Then there are lots of manual subscription trackers

This category is extremely crowded.

For example, **Bobby** has existed for years. Users manually enter subscriptions, and Bobby calculates spending and reminds them before bills are due. Its Indian App Store listing currently has **343 ratings with 4.6/5**. (Sources: [Bobby on App Store](https://apps.apple.com/in/app/bobby-track-subscriptions/id1059152023?platform=watch))

There are numerous similar apps:

- Subby
- SubManager
- SubGuard
- SubTrack
- Subscription Manager
- SubSenda
- Subly
- RecurTrack

Their basic workflow is generally:

**User remembers subscription → enters it → app reminds user.**

That's fundamentally different from your problem.

Your problem occurred precisely because:

> **you didn't remember the subscription existed.**

So a manual tracker has a structural flaw for your particular JTBD.

**Confidence: High.**

---

# 9. Apple and Google partially solve it—but only inside their ecosystems

Apple lets users see and cancel subscriptions **billed by Apple/App Store**. But Apple explicitly tells users that if they can't find a subscription there, they may have bought it directly from another company and should check the bank/card statement. (Sources: [Apple Support](https://support.apple.com/en-us/118428))

Google Play similarly has a Subscription Center for subscriptions using Google Play billing. (Sources: [Google Help](https://support.google.com/googleplay/answer/11174377?hl=en), [Google Help](https://support.google.com/googleplay/answer/7018481?hl=en-IN))

So neither gives you:

> Netflix direct + SaaS tools + newspaper + gym + web trial + App Store + Play Store + etc.

in one universal view.

And Gmail's new **“Manage subscriptions”** feature is misleadingly named for this use case: it manages **email mailing lists/newsletters**, not paid recurring subscriptions. (Sources: [Google Help](https://support.google.com/mail/answer/15621070?co=GENIE.Platform%3DAndroid&hl=en))

**Confidence: High.**

---

# 10. So is the idea already taken?

### Yes — the mechanism exists.

**Confidence: High.**

There are already several products doing:

**Gmail → automatically detect subscriptions → track → remind.**

Therefore I would **not** position the proposed product around:

> “An app that scans Gmail and finds your subscriptions.”

That feature alone is no longer differentiated.

But I would **not conclude the opportunity is gone.**

The pattern I'm seeing is:

### 🟢 Established demand

Rocket Money has demonstrated that subscription discovery/management can be a very large consumer need. (Sources: [Rocket Money on Google Play](https://play.google.com/store/apps/details/Truebill_Budget_Planner_Bill_Tracker_and_Reminder?hl=en_IN&id=com.truebill))

### 🟡 Established manual trackers

There are many, but they don't solve forgotten subscriptions particularly well.

### 🔴 Gmail-first competitors are mostly tiny/new

The Gmail-first products I could verify are overwhelmingly early-stage:

- SubRadar: insufficient App Store ratings
- BeforeItBills: insufficient App Store ratings
- Substrack: 10+ Play Store downloads
- Subcut: 2 Indian App Store ratings

None of those signals resembles a market leader. (Sources: [BeforeItBills on App Store](https://apps.apple.com/be/app/beforeitbills/id6760515650), [Subcut on App Store](https://apps.apple.com/in/app/subcut-subscription-tracker/id6758765733), [SubRadar on App Store](https://apps.apple.com/in/app/subradar-subscription-manager/id6758894751), [Substrack on Google Play](https://play.google.com/store/apps/details?id=com.kimekolab.substrack))

That distinction matters enormously.

---

# 11. What I think the competitive map actually looks like

```text
                    AUTOMATIC DISCOVERY
                           ↑
                           │
              BeforeItBills
              SubRadar
              Subzero
              Subwise 🇮🇳
              Subcut
                           │
BANK DATA  ←──── Rocket Money ─────────→ EMAIL DATA
                           │
                           │
               Bobby / Subby /
               SubManager etc.
                           │
                           ↓
                     MANUAL ENTRY
```

There isn't an obvious **“Rocket Money of Gmail subscription tracking”** yet.

And particularly in India, bank-based aggregation has a structural disadvantage because the dominant US solution depends on financial-data connectivity that doesn't map cleanly onto Indian banks. Gmail receipts, UPI mandate emails, card emails and merchant emails potentially provide an alternative data layer. Plaid's current documented institution country codes, for example, do not include India. (Sources: [Plaid docs](https://plaid.com/docs/api/institutions/))

**Confidence: Medium-High on the strategic conclusion.** The factual inputs are high-confidence; determining whether the absence of a dominant player represents an attractive business opportunity requires user/adoption research beyond competitor presence alone.

---

## 12. One major caveat for your product

There is a technical/business issue worth knowing **before** committing to Gmail as the foundation.

`gmail.readonly` is classified by Google as a **restricted OAuth scope**. (Sources: [Google Developers](https://developers.google.com/workspace/gmail/api/auth/scopes))

For a production consumer application using restricted Gmail access, Google requires OAuth verification, and applications storing or transmitting restricted-scope data can require a security assessment. Google says restricted-scope apps may also need **annual security assessment/re-verification**. (Sources: [Google Help](https://support.google.com/cloud/answer/13463073?hl=en), [Google Help](https://support.google.com/cloud/answer/13464325?hl=en), [Google Help](https://support.google.com/cloud/answer/13465431?hl=en))

This isn't a blocker—multiple products above clearly use Gmail—but it means:

**“We'll just connect Gmail” isn't quite as lightweight operationally as it sounds.**

---

# My takeaway for your idea

I would update our earlier problem exploration based on this research.

**Do not abandon the idea. But stop treating Gmail scanning as the product. Treat it as the data-acquisition mechanism.**

The unsolved product question is more interesting:

> **“How do I make it practically impossible for a consumer to be unexpectedly charged for a subscription they no longer consciously want?”**

That potentially involves much more than simply listing subscriptions:

**discover → understand status → identify free trial/renewal → identify unusual annual renewals → tell user at the right moment → make decision effortless → help them cancel → verify cancellation → continue monitoring.**

That end-to-end **“never get surprised by an auto-renewal again”** outcome is a stronger product thesis than **“subscription tracker.”**

And importantly, **none of the research so far gives me high confidence that someone has won that consumer experience, particularly for India.** 🔎

If you'd like, the next useful step is for me to turn this into a **proper competitor teardown of the 5 closest products—screens, onboarding, detection approach, pricing, strengths, weaknesses, and exactly where an MVP could differentiate.**

---

If you want, I can:

- Analyze competitor features and user experience details
- Explore strategic opportunities for subscription tracking in India
- Examine technical and operational challenges of using Gmail API
