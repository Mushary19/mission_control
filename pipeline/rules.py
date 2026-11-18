"""Rule table: text -> (category, activity, process, extracted fields).

One table so the README can show it. Rules are tried top to bottom; the first match wins.
Matching is case-insensitive on: `subject` (mail subject / meeting subject), `text` (plain body),
`title` (screen window title), `url` (screen url).

Each rule says where the subject person comes from (`who`), in priority order:
  sender      the actor of the event
  recipient   the first non-staff To recipient (mail) / non-staff attendee (calendar)
  chat_other  the other member of a 1:1 Teams chat
  text        a name written in the text (named groups `name` / `sname`)
  thread      inherited from an earlier process event in the same thread
  chat_pair   (it_ready only) the latest open it_requested in the same chat
  none        no name in the record; linked later by time / case logic (Phase 2)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ----------------------------------------------------------------------------- building blocks

DAY = r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)"
MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
DATE = rf"{DAY} \d{{1,2}} {MON}"
DATES = rf"{DATE}(?: – {DATE})?"
NAME = r"[^\W\d_][\w'’.\- ]*?"  # a person name as written (letters, spaces, dots, hyphens)
LEAVE_TYPE = r"annual leave|sick leave|a personal day"


@dataclass(frozen=True)
class Rule:
    id: str
    category: str  # process | context | noise | out_of_scope
    sources: tuple[str, ...]
    activity: str | None = None
    process: str | None = None
    subject: str | None = None
    text: str | None = None
    title: str | None = None
    url: str | None = None
    sender_domain: str | None = None
    direction: str | None = None  # "in" (from outside staff) | "out" (from staff) | None
    reply: bool | None = None  # channel: True = reply only, False = root only
    who: tuple[str, ...] = ()
    likely: bool = False  # screen-derived: shows what was open, not what was done
    reason: str | None = None  # for noise / out_of_scope / context
    label: str | None = None  # human label for the UI
    _compiled: dict = field(default_factory=dict, compare=False, repr=False)

    def rx(self, key: str):
        pat = getattr(self, key)
        if pat is None:
            return None
        if key not in self._compiled:
            self._compiled[key] = re.compile(pat, re.IGNORECASE | re.MULTILINE)
        return self._compiled[key]


MAIL = ("mail",)
TEAMS = ("teams_chat",)
CHANNEL = ("teams_channel",)
CAL = ("calendar",)
SCREEN = ("screen",)

R = Rule
RULES: list[Rule] = [
    # ======================================================================= NOISE
    # Teams small talk
    *[
        R(f"noise_chat_{i}", "noise", TEAMS, text=p, reason="small talk")
        for i, p in enumerate(
            [
                r"^\s*lunch\?\s*$",
                r"^\s*coffee\b",
                r"^\s*thanks!\s*$",
                r"^\s*👍\s*$",
                r"^\s*running \d+ min late\s*$",
                r"^\s*are you joining the sync\?\s*$",
                r"^\s*can you cover my inbox for an hour\s*$",
                r"^\s*the VPN is slow again\s*$",
                r"^\s*did you see .+ message\?\s*$",
                r"^\s*who's updating the tracker today\?\s*$",
            ]
        )
    ],
    R("noise_newsletter", "noise", MAIL, sender_domain=r"(hrbrew|hiretrack|linkedin)\.example", reason="newsletter"),
    R("noise_channel_general", "noise", CHANNEL, reason="General channel post"),  # matched by channel name in pipeline
    # Screens: noise by title/url (app field is not reliable)
    R("noise_screen_bbc", "noise", SCREEN, url=r"bbc\.example", reason="news site"),
    R("noise_screen_youtube", "noise", SCREEN, url=r"youtube\.example", reason="YouTube"),
    R("noise_screen_spotify", "noise", SCREEN, title=r"^Spotify", reason="Spotify"),
    R("noise_screen_lock", "noise", SCREEN, title=r"Lock Screen", reason="lock screen"),
    R("noise_screen_linkedin_feed", "noise", SCREEN, url=r"linkedin\.example/feed", reason="LinkedIn feed"),
    R("noise_screen_google", "noise", SCREEN, title=r"^Google Search$", reason="Google Search"),
    R("noise_screen_timeanddate", "noise", SCREEN, url=r"timeanddate\.example", reason="timeanddate"),
    R("noise_screen_explorer", "noise", SCREEN, title=r" - File Explorer$", reason="File Explorer"),
    # ======================================================================= OUT OF SCOPE
    # Mail: payslip / timesheet / invoice queries
    R("oos_mail_payroll", "out_of_scope", MAIL, subject=r"^(RE: )?(Payslip|Timesheet|Timesheet query|Invoice question) –", reason="payslip / timesheet / invoice query"),
    # Mail: recruitment (HireTrack / Recruitment tracker are out of scope)
    R("oos_mail_recruit", "out_of_scope", MAIL, subject=r"(^(RE: )?Your application –|opportunity – Harbourline|^(RE: )?Offer –|^Feedback –|^(RE: )?Shortlist –|^New requirement –|^Application –|^Missed you today|no suitable candidates)", reason="recruitment (seen, not modelled)"),
    # Mail: birthday gifts
    R("oos_mail_gift", "out_of_scope", MAIL, sender_domain=r"hamperly\.example", reason="birthday gifts (seen, not modelled)"),
    R("oos_mail_gift_invoice", "out_of_scope", MAIL, subject=r"^Gift invoice", reason="birthday gifts (seen, not modelled)"),
    # Teams: recruitment + gifts
    R("oos_chat_recruit", "out_of_scope", TEAMS, text=r"(^Spoke to .+ for the .+ role|is filled – .+ accepted|^New one from )", reason="recruitment (seen, not modelled)"),
    R("oos_chat_gift", "out_of_scope", TEAMS, text=r"^Gift on its way for", reason="birthday gifts (seen, not modelled)"),
    # Channel: laptop replacement (root; replies inherit in the pipeline)
    R("oos_channel_replacement", "out_of_scope", CHANNEL, reply=False, text=r"^Laptop needed for .+ \(replacement\)", reason="laptop replacement (seen, not modelled)"),
    # Calendar
    R("oos_cal_sync", "out_of_scope", CAL, subject=r"^Weekly People team sync$", reason="team meeting"),
    R("oos_cal_1on1", "out_of_scope", CAL, subject=r"^1:1 ", reason="1:1 meeting"),
    R("oos_cal_focus", "out_of_scope", CAL, subject=r"^Focus time$", reason="focus time"),
    R("oos_cal_recruit", "out_of_scope", CAL, subject=r"^(Screening call|Interview:)", reason="recruitment (seen, not modelled)"),
    R("oos_cal_birthday", "out_of_scope", CAL, subject=r"birthday$", reason="birthday reminder (all-day; gifts not modelled)"),
    # Screens
    R("oos_screen_hiretrack", "out_of_scope", SCREEN, url=r"hiretrack\.example", reason="recruitment (HireTrack)"),
    R("oos_screen_rtracker", "out_of_scope", SCREEN, title=r"^Recruitment tracker\.xlsx", reason="recruitment (Recruitment tracker)"),
    R("oos_screen_linkedin_talent", "out_of_scope", SCREEN, url=r"linkedin\.example/(talent|messaging)", reason="recruitment (LinkedIn)"),
    R("oos_screen_hamperly", "out_of_scope", SCREEN, url=r"hamperly\.example", reason="birthday gifts"),
    R("oos_screen_recruit_mail", "out_of_scope", SCREEN, title=r"(Your application –|opportunity – Harbourline|^(RE: )?Offer –|^(RE: )?Shortlist –|^Missed you today|no suitable candidates|^Gift invoice).* - Message \(HTML\)$", reason="recruitment / gifts mail open"),
    # ======================================================================= LEAVE
    R("leave_requested_chat", "process", TEAMS, "leave_requested", "leave", text=rf"can I take (?P<type>{LEAVE_TYPE}) on (?P<dates>{DATES})", who=("sender",), label="Leave requested"),
    R("leave_requested_mail", "process", MAIL, "leave_requested", "leave", direction="in", subject=rf"^Leave request – (?P<dates>{DATES})$", text=rf"I'd like to request (?P<type>{LEAVE_TYPE}) for (?P<dates2>{DATES})", who=("sender",), label="Leave requested"),
    R("leave_client_check", "process", MAIL, "client_check_sent", "leave", direction="out", subject=rf"^Leave request – (?P<sname>{NAME}) – (?P<dates>{DATES})$", text=rf"^\s*(?P<name>{NAME}) has asked for (?P<type>{LEAVE_TYPE}) on (?P<dates2>{DATES})\. Is that ok on your side\?", who=("text",), label="Client asked"),
    R("leave_client_sick", "process", MAIL, "client_notified_sick", "leave", direction="out", subject=rf"^(?P<sname>{NAME}) – sick leave (?P<dates>{DATES})$", text=rf"^\s*(?P<name>{NAME}) is unwell and off (?P<dates2>{DATES})", who=("text",), label="Client told (sick)"),
    R("leave_client_approved", "process", MAIL, "client_approved", "leave", direction="in", subject=rf"^RE: Leave request – (?P<sname>{NAME}) – (?P<dates>{DATES})$", text=r"(Approved, thanks|Yes, that's fine|No problem)", who=("thread", "text"), label="Client approved"),
    R("leave_client_declined", "process", MAIL, "client_declined", "leave", direction="in", subject=rf"^RE: Leave request – (?P<sname>{NAME}) – (?P<dates>{DATES})$", text=r"could they pick other dates", who=("thread", "text"), label="Client declined"),
    R("leave_worker_approved", "process", MAIL + TEAMS, "worker_approved", "leave", direction="out", text=rf"Your leave for (?P<dates>{DATES}) is approved", who=("recipient", "chat_other", "thread"), label="Worker told: approved"),
    R("leave_worker_other_dates", "process", MAIL + TEAMS, "worker_asked_other_dates", "leave", direction="out", text=r"The client asked if you could choose other dates", who=("recipient", "chat_other", "thread"), label="Worker asked for other dates"),
    R("leave_cancel", "process", MAIL + TEAMS, "cancel_requested", "leave", direction="in", text=rf"won't need the leave on (?P<dates>{DATES}) after all", who=("sender",), label="Cancel requested"),
    R("leave_peoplehub", "process", SCREEN, "peoplehub_opened", "leave", title=r"^Leave - (?P<name>.+) - PeopleHub$", who=("text",), likely=True, label="PeopleHub opened"),
    R("leave_tracker", "process", SCREEN, "tracker_updated", "leave", title=r"^Leave tracker 2026\.xlsx", who=("none",), likely=True, label="Leave tracker updated"),
    # ======================================================================= OFFBOARDING
    R("off_resignation", "process", MAIL, "resignation_received", "offboarding", direction="in", subject=r"^Resignation$", text=rf"my last working day will be (?P<last_day>{DATE})", who=("sender",), label="Resignation received"),
    R("off_client_ended", "process", MAIL, "client_ended_engagement", "offboarding", direction="in", subject=rf"^(?P<sname>{NAME}) – end of engagement$", text=rf"last day (?P<last_day>{DATE})", who=("text",), label="Client ended engagement"),
    R("off_ack", "process", MAIL, "offboarding_acknowledged", "offboarding", direction="out", text=r"(I'll send the next steps shortly|we'll handle the offboarding)", who=("thread", "recipient"), label="Offboarding acknowledged"),
    R("off_access", "process", TEAMS, "access_disable_requested", "offboarding", direction="out", text=rf"^\s*(?P<name>{NAME}) finishes (?P<last_day>{DATE}), can you disable access", who=("text",), label="Access removal requested"),
    R("off_return", "process", MAIL, "laptop_return_arranged", "offboarding", direction="out", subject=r"^Returning your laptop$", who=("recipient",), label="Laptop return arranged"),
    R("off_courier_delivered", "process", MAIL, "courier_delivered", "offboarding", sender_domain=r"swiftparcel\.example", subject=r"^Delivered: consignment (?P<consignment>SP\d+)", who=("none",), likely=True, label="Courier delivered"),
    R("off_laptop_received", "process", TEAMS, "laptop_received", "offboarding", direction="in", text=rf"Got (?P<name>{NAME})['’]s laptop back, wiped", who=("text",), label="Laptop received"),
    R("off_completed", "process", MAIL, "offboarding_completed", "offboarding", direction="out", subject=rf"^Offboarding complete – (?P<sname>{NAME})$", who=("text",), label="Offboarding completed"),
    R("off_courier_booked", "process", SCREEN, "courier_booked", "offboarding", title=r"^Book a pickup \| SwiftParcel", who=("none",), likely=True, label="Courier booked"),
    # ======================================================================= ONBOARDING
    R("on_contract_sent", "process", MAIL, "contract_sent", "onboarding", direction="out", subject=r"^Your contractor agreement – Harbourline Talent$", who=("recipient",), label="Contract sent"),
    R("on_contract_reminder", "process", MAIL, "contract_reminder", "onboarding", direction="out", text=r"Just a gentle reminder about the agreement", who=("recipient", "thread"), label="Contract reminder"),
    R("on_contract_signed", "process", MAIL, "contract_signed", "onboarding", direction="in", text=r"Signed copy attached", who=("sender",), label="Contract signed"),
    R("on_training_mail", "process", MAIL, "training_enrolled", "onboarding", direction="out", subject=r"^Pre-start training modules$", who=("recipient",), label="Training enrolled"),
    R("on_training_screen", "process", SCREEN, "training_enrolled", "onboarding", title=r"^Learners - Harbourline Academy", who=("none",), likely=True, label="Training enrolled"),
    R("on_induction_meeting", "process", CAL, "induction_meeting", "onboarding", subject=rf"^Induction – (?P<name>{NAME})$", who=("recipient", "text"), label="Induction meeting"),
    R("on_induction_done", "process", TEAMS, "induction_completed", "onboarding", direction="out", text=rf"^\s*(?P<name>{NAME}) finished induction, good to go for (?P<client>.+?)\s*$", who=("text",), label="Induction completed"),
    R("on_welcome", "process", MAIL, "welcome_sent", "onboarding", direction="out", subject=r"^Welcome to Harbourline Talent!", text=rf"first day with (?P<client>.+?) is (?P<first_day>{DATE})", who=("recipient",), label="Welcome sent"),
    R("on_laptop_requested", "process", CHANNEL, "laptop_requested", "onboarding", reply=False, text=rf"^\s*Laptop needed for (?P<name>{NAME}) \(new starter\), (?P<client>[^,]+), needed by (?P<needed_by>{DATE})", who=("text",), label="Laptop requested"),
    R("on_laptop_quote", "process", CHANNEL, "laptop_quote", "onboarding", reply=True, text=r"^\s*(?P<model>.+?) from (?P<vendor>\w+), ~(?P<amount>\d+) AUD, ok\?", who=("thread",), label="Laptop quote"),
    R("on_laptop_approved", "process", CHANNEL, "laptop_approved", "onboarding", reply=True, text=r"^\s*(Approved|ok approved|Go ahead)\b", who=("thread",), label="Laptop approved"),
    R("on_laptop_delivered", "process", CHANNEL, "laptop_delivered", "onboarding", reply=True, text=rf"^\s*(?P<name>{NAME}) has the laptop now", who=("thread", "text"), label="Laptop delivered"),
    R("on_it_requested", "process", TEAMS, "it_requested", "onboarding", direction="out", text=rf"can you set up M365, VPN and the timesheet app for (?P<name>{NAME})\? Starts (?P<first_day>{DATE}) at (?P<client>.+?)\s*$", who=("text",), label="IT setup requested"),
    R("on_it_ready_named", "process", TEAMS, "it_ready", "onboarding", direction="in", text=rf"^\s*all set for (?P<name>{NAME})\s*$", who=("chat_pair", "text"), label="IT ready"),
    R("on_it_ready_anon", "process", TEAMS, "it_ready", "onboarding", direction="in", text=r"^\s*(Accounts created|Done, temp password sent to their personal email)", who=("chat_pair",), label="IT ready"),
    R("on_kickoff", "process", CAL, "kickoff_meeting", "onboarding", subject=rf"^Kick-off: (?P<name>{NAME}) x (?P<client>.+)$", who=("text", "recipient"), label="Client kick-off"),
    # vendor mails + starter confirmation. New starters only: the pipeline moves replacements to out_of_scope
    R("on_laptop_ordered", "process", MAIL, "laptop_ordered", "onboarding", sender_domain=r"(lapworks|techdirect)\.example", subject=r"^Order confirmation (?P<order_no>[A-Z]{2}-\d+)$", text=rf"\d+ x (?P<model>[^\n]+)\nDeliver to: (?P<name>{NAME})\s*$", who=("text",), label="Laptop ordered"),
    R("on_laptop_shipped", "process", MAIL, "laptop_shipped", "onboarding", sender_domain=r"(lapworks|techdirect)\.example", subject=r"^Your order (?P<order_no>[A-Z]{2}-\d+) has shipped$", text=r"Tracking: (?P<tracking>SP\d+)", who=("thread",), label="Laptop shipped"),
    R("on_laptop_confirmed", "process", TEAMS, "laptop_confirmed_by_starter", "onboarding", direction="in", text=r"(the new laptop is here|^\s*Laptop arrived, thank you)", who=("sender",), label="Starter confirmed laptop"),
    R("on_day_one_reply","process", MAIL, "day_one_reply", "onboarding", direction="in", subject=r"^RE: How was day one\?", who=("sender",), label="Day-one reply"),
    R("on_day_one_checkin", "process", MAIL, "day_one_checkin", "onboarding", direction="out", subject=r"^How was day one\?", who=("recipient",), label="Day-one check-in"),
    R("on_onboarded", "process", TEAMS, "onboarded_confirmed", "onboarding", direction="out", text=rf"^\s*(?P<name>{NAME}) onboarded at (?P<client>.+?) ✅", who=("text",), label="Onboarded confirmed"),
    # ======================================================================= CONTEXT (kept, never a case step)
    R("ctx_screen_inbox", "context", SCREEN, title=r"^Inbox - .+ - Outlook$", reason="generic: Outlook inbox"),
    R("ctx_screen_chat", "context", SCREEN, title=r"^Chat \| .*Microsoft Teams$", reason="generic: Teams chat"),
    R("ctx_screen_activity", "context", SCREEN, title=r"^Activity \| ", reason="generic: Teams activity"),
    R("ctx_screen_mail_open", "context", SCREEN, title=r" - Message \(HTML\)$", reason="mail window open (the mail itself is the evidence)"),
    R("ctx_screen_vendor", "context", SCREEN, url=r"(lapworks|techdirect)\.example", reason="laptop vendor page (no rule: procurement not modelled from screens)"),
]

# Activity -> human label (first label wins)
ACTIVITY_LABELS: dict[str, str] = {}
for _r in RULES:
    if _r.activity and _r.label and _r.activity not in ACTIVITY_LABELS:
        ACTIVITY_LABELS[_r.activity] = _r.label

# day-one reply mentions an open problem
DAY_ONE_ISSUE = re.compile(r"(still waiting|missing|not working|no access)", re.IGNORECASE)

# Staff vocabulary used for "process-like but unmatched" detection in the report
PROCESS_HINT = re.compile(
    r"(leave|laptop|induction|onboard|offboard|access|contract|courier|consignment|order|resign|"
    r"engagement|sick|starter|accounts?|password|M365|VPN|welcome|first day|deliver|shipped|arrived)",
    re.IGNORECASE,
)
