"""Claude's own stage-3/4 answers for the synthetic fixtures (written in-session,
following prompts.EXTRACT_SYSTEM). Used to exercise --provider replay."""
import json
from pathlib import Path

N = {"value": None, "quote": None}


def q(v, s):
    return {"value": v, "quote": s}


def ex(etype, merchant, kind=N, period=None, amount=None, charge=N, nxt=N, trial_end=N, trial_len=N, cancel=N):
    return {
        "is_subscription_related": True, "email_type": etype, "merchant": q(merchant, None), "kind": kind,
        "billing_period": {"value": None, "period_months": None, "quote": None} if period is None else period,
        "amount": {"value": None, "currency": None, "quote": None} if amount is None else amount,
        "charge_date": charge, "next_charge_date": nxt, "trial_end_date": trial_end,
        "trial_length_days": trial_len, "cancel_path": cancel,
    }


def per(v, s, months=None):
    return {"value": v, "period_months": months, "quote": s}


def amt(v, c, s):
    return {"value": v, "currency": c, "quote": s}


A = []


def add(mid, triage, extraction=None):
    A.append({"message_id": mid, "triage": triage, "extraction": extraction})


for mid, charged_iso, charged, nxt_iso, nxt in [
    ("sf-10", "2026-10-05", "5 October 2026", "2026-11-05", "5 November 2026"),
    ("sf-09", "2026-09-05", "5 September 2026", "2026-10-05", "5 October 2026"),
    ("sf-08", "2026-08-05", "5 August 2026", "2026-09-05", "5 September 2026"),
]:
    s = f"We charged ₹649 for your StreamFlix Premium monthly plan on {charged}."
    add(mid, True, ex("receipt", "StreamFlix", q("subscription", s), per("monthly", s), amt(649, "INR", s),
                      q(charged_iso, s), q(nxt_iso, f"Your next billing date is {nxt}."),
                      cancel=q("https://streamflix.example/account/cancel",
                               "Manage or cancel your membership at https://streamflix.example/account/cancel")))

s = "After your trial, you'll be charged ₹119 per month unless you cancel."
add("tb-1", True, ex("trial_signup", "TuneBox", q("trial", "Your 30-day free trial has started."), per("monthly", s),
                     amt(119, "INR", s), trial_len=q(30, "Your 30-day free trial has started."),
                     cancel=q("https://tunebox.example/account/cancel", "Cancel anytime at https://tunebox.example/account/cancel")))
add("pf-1", True, ex("trial_signup", "PixelForge", q("trial", "Your PixelForge Pro trial is now active.")))
add("cn-1", True, ex("receipt", "CloudNote", q("subscription", "Your CloudNote Plus annual subscription has been renewed."),
                     per("annual", "Your CloudNote Plus annual subscription has been renewed."),
                     amt(59.99, "USD", "Amount charged: $59.99 USD."), q("2026-01-14", "Payment date: 2026-01-14."),
                     q("2027-01-14", "Your subscription will renew on 2027-01-14.")))
add("dh-1", True, ex("renewal_reminder", "DomainHub", q("renewal", "Your domain myblog.example is due for renewal."),
                     per("annual", "Renewal price: ₹1,299 per year."), amt(1299, "INR", "Renewal price: ₹1,299 per year."),
                     nxt=q("2026-12-12", "It expires on 12 December 2026.")))
s = "Your policy SL-4471 premium of Rs. 18,500 is due on 28/11/2026."
add("sl-1", True, ex("renewal_reminder", "SafeLife Insurance", q("renewal", s), per("annual", "This is an annual premium."),
                     amt(18500, "INR", s), nxt=q("2026-11-28", s)))
s = "We charged ₹999 for your GymPass monthly membership on 1 June 2026."
add("gp-1", True, ex("receipt", "GymPass", q("subscription", s), per("monthly", s), amt(999, "INR", s), q("2026-06-01", s)))
add("gp-2", True, ex("cancellation_confirmation", "GymPass"))
add("gp-3", True, ex("winback_offer", "GymPass"))
s = "We charged ₹199 for your NewsDaily Digital monthly subscription on 15 September 2026."
add("nd-1", True, ex("receipt", "NewsDaily", q("subscription", s), per("monthly", s), amt(199, "INR", s), q("2026-09-15", s)))
s = "The price of your monthly subscription will change from ₹199 to ₹249 starting 15 December 2026."
add("nd-2", True, ex("price_change", "NewsDaily", q("subscription", s), per("monthly", s), amt(249, "INR", s)))
for mid, price, d_iso, d in [("vm-1", 299, "2026-07-03", "3 July 2026"), ("vm-2", 349, "2026-10-03", "3 October 2026")]:
    s = f"We charged ₹{price} for your VidMax monthly plan on {d}."
    add(mid, True, ex("receipt", "VidMax", q("subscription", s), per("monthly", s), amt(price, "INR", s), q(d_iso, s)))
s = "We charged ₹1,500 for your LearnLab quarterly plan on 1 October 2026."
add("ll-1", True, ex("receipt", "LearnLab", q("subscription", s), per("other", s, 3), amt(1500, "INR", s), q("2026-10-01", s)))
add("kv-1", True, ex("receipt", "KeyVault", q("subscription", "Your KeyVault Family annual plan is active."),
                     per("annual", "Your KeyVault Family annual plan is active."), amt(2999, "INR", "Total: ₹2,999")))
add("hn-1", True, ex("receipt", "HostNest",
                     q("subscription", "Please find your invoice for your HostNest subscription attached.")))
for mid in ("sk-1", "nl-1", "otp-1", "inj-1"):  # one-off order, newsletter, OTP, prompt-injection attempt
    add(mid, False)

out = Path(__file__).with_name("claude_answers_synthetic.jsonl")
out.write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in A))
print(f"wrote {len(A)} answers to {out}")
