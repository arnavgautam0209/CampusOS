"""
Session attendance reports (JSON, PDF, CSV). Read-only: nothing here creates
or changes attendance.

Present means an AttendanceRecord exists for that session; everyone else on
the roster is absent. Nobody is ever marked present by default.

Roster policy: a session's roster is every enrollment in its classroom that
was current at some point while the session ran, i.e. enrolled_at is before
the session ended (or now, while it's open) and left_at is empty or after it
opened. Because enrollments are ended with left_at rather than deleted, the
roster of a closed session never changes afterwards: students enrolled later
aren't added and students who leave later stay on it. Reports for open
sessions are provisional.

Attendees with a record but no enrollment (e.g. a card registered without
--classroom) are listed separately and don't count towards the totals.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from xml.sax.saxutils import escape

from django.db.models import Q
from django.utils import timezone

from .models import AttendanceRecord, AttendanceSession, ClassroomEnrollment
from .services import display_name


@dataclass
class ReportStudent:
    roll_number: str
    name: str
    username: str
    marked_at: Optional[datetime] = None
    source: Optional[str] = None   # "card" or "manual"; None for absent students
    card_uid: Optional[str] = None


@dataclass
class SessionReport:
    session: AttendanceSession
    generated_at: datetime
    is_final: bool
    present: List[ReportStudent] = field(default_factory=list)
    absent: List[ReportStudent] = field(default_factory=list)
    not_enrolled: List[ReportStudent] = field(default_factory=list)

    @property
    def total(self):
        return len(self.present) + len(self.absent)

    @property
    def percentage(self):
        """None for an empty roster (no division by zero, and 0% would be misleading)."""
        return round(len(self.present) * 100 / self.total, 1) if self.total else None

    @property
    def faculty(self):
        return display_name(self.session.opened_by) if self.session.opened_by else None

    @property
    def filename_stem(self):
        room = re.sub(r"[^A-Za-z0-9-]+", "-", self.session.classroom_id).strip("-") or "Room"
        return f"AttendX_{room}_Session_{self.session.id:02d}"


def roster_for(session, now=None):
    end = session.closed_at or now or timezone.now()
    enrollments = (
        ClassroomEnrollment.objects
        .filter(classroom_id=session.classroom_id, enrolled_at__lte=end)
        .filter(Q(left_at__isnull=True) | Q(left_at__gt=session.opened_at))
        .select_related("student")
        .order_by("enrolled_at")
    )
    # A student who left and re-enrolled has two rows: the latest roll number wins.
    return {enrollment.student_id: enrollment for enrollment in enrollments}


def build_report(session, now=None):
    now = now or timezone.now()
    roster = roster_for(session, now)
    records = {
        record.student_id: record
        for record in AttendanceRecord.objects.filter(session=session).select_related("student", "card")
    }
    report = SessionReport(session=session, generated_at=now, is_final=session.closed_at is not None)

    for student_id, enrollment in roster.items():
        student = enrollment.student
        record = records.get(student_id)
        entry = ReportStudent(enrollment.roll_number, display_name(student), student.get_username())
        if record is None:
            report.absent.append(entry)
        else:
            _fill_attendance(entry, record)
            report.present.append(entry)

    for student_id, record in records.items():
        if student_id not in roster:
            entry = ReportStudent("", display_name(record.student), record.student.get_username())
            _fill_attendance(entry, record)
            report.not_enrolled.append(entry)

    report.present.sort(key=lambda s: (s.roll_number, s.name))
    report.absent.sort(key=lambda s: (s.roll_number, s.name))
    report.not_enrolled.sort(key=lambda s: s.marked_at)
    return report


def _fill_attendance(entry, record):
    entry.marked_at = record.marked_at
    entry.source = record.source
    # Only card scans carry a card; faculty-added records are never shown as scans.
    entry.card_uid = record.card.uid if record.source == AttendanceRecord.Source.CARD and record.card else None


# MARK: JSON

def report_json(report):
    session = report.session

    def student(entry, present):
        data = {"rollNumber": entry.roll_number, "name": entry.name, "username": entry.username,
                "status": "present" if present else "absent"}
        if present:
            data.update(markedAt=entry.marked_at.isoformat(), source=entry.source, cardUid=entry.card_uid)
        return data

    return {
        "session": {
            "id": session.id, "title": session.title,
            "openedAt": session.opened_at.isoformat(),
            "closedAt": session.closed_at.isoformat() if session.closed_at else None,
            "status": "final" if report.is_final else "provisional",
        },
        "classroom": {"id": session.classroom_id, "name": session.classroom.name},
        "faculty": {"name": report.faculty,
                    "username": session.opened_by.get_username() if session.opened_by else None},
        "summary": {"totalStudents": report.total, "present": len(report.present),
                    "absent": len(report.absent), "attendancePercentage": report.percentage},
        "presentStudents": [student(e, True) for e in report.present],
        "absentStudents": [student(e, False) for e in report.absent],
        "notEnrolledAttendees": [student(e, True) for e in report.not_enrolled],
        "generatedAt": report.generated_at.isoformat(),
        "rosterPolicy": "Students enrolled in the classroom at any time while the session was open.",
    }


# MARK: CSV

def report_csv(report):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Session ID", "Session", "Classroom", "Status", "Roll Number", "Name", "Marked At",
                     "Method"])
    base = [report.session.id, report.session.title, report.session.classroom_id]
    for entry in report.present:
        writer.writerow(base + ["PRESENT", entry.roll_number, entry.name, entry.marked_at.isoformat(),
                                _method(entry)])
    for entry in report.absent:
        writer.writerow(base + ["ABSENT", entry.roll_number, entry.name, "", ""])
    for entry in report.not_enrolled:
        writer.writerow(base + ["PRESENT (NOT ENROLLED)", "", entry.name, entry.marked_at.isoformat(),
                                _method(entry)])
    return out.getvalue()


def _method(entry):
    return "RFID card" if entry.source == AttendanceRecord.Source.CARD else "Added by faculty"


# MARK: PDF

def _local(value):
    return timezone.localtime(value).strftime("%d %b %Y, %H:%M:%S %Z") if value else "—"


def report_pdf(report):
    """A4 PDF as bytes."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    session = report.session
    styles = getSampleStyleSheet()
    brand = ParagraphStyle("brand", parent=styles["Title"], fontSize=18, spaceAfter=2,
                           textColor=colors.HexColor("#3730A3"))
    subtitle = ParagraphStyle("subtitle", parent=styles["Heading2"], alignment=TA_CENTER, spaceBefore=0,
                              textColor=colors.HexColor("#334155"))
    heading = ParagraphStyle("heading", parent=styles["Heading3"], spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=9, leading=11)
    small = ParagraphStyle("small", parent=body, fontSize=8, textColor=colors.HexColor("#64748B"))
    width = A4[0] - 36 * mm

    def table(rows, widths, header_color):
        result = Table(rows, colWidths=[w * width for w in widths], repeatRows=1)
        result.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), header_color),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return result

    def cell(text, markup=False):
        # Names and titles are data: escape them so "<" or "&" can't break the layout.
        return Paragraph(text if markup else escape(text), body)

    story = [
        Paragraph("CAMPUSOS — ATTENDX", brand),
        Paragraph("Session Attendance Report" if report.is_final
                  else "Session Attendance Report (PROVISIONAL: session still open)", subtitle),
        Spacer(1, 6),
    ]
    details = [
        ["Classroom", f"{session.classroom.name} ({session.classroom_id})", "Session ID", str(session.id)],
        ["Session", session.title, "Faculty", report.faculty or "—"],
        ["Started", _local(session.opened_at), "Ended", _local(session.closed_at) if session.closed_at
         else "Still open"],
    ]
    info = Table([[cell(f"<b>{a}</b>", True), cell(b), cell(f"<b>{c}</b>", True), cell(d)] for a, b, c, d in details],
                 colWidths=[0.16 * width, 0.42 * width, 0.14 * width, 0.28 * width])
    info.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LINEBELOW", (0, -1), (-1, -1), 0.6, colors.HexColor("#CBD5E1"))]))
    story += [info, Spacer(1, 8)]

    percentage = "N/A" if report.percentage is None else f"{report.percentage:g}%"
    summary = Table([["Total Students", "Present", "Absent", "Attendance"],
                     [str(report.total), str(len(report.present)), str(len(report.absent)), percentage]],
                    colWidths=[width / 4] * 4)
    summary.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, 0), 9), ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#64748B")),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"), ("FONTSIZE", (0, 1), (-1, 1), 16),
        ("TEXTCOLOR", (1, 1), (1, 1), colors.HexColor("#15803D")),
        ("TEXTCOLOR", (2, 1), (2, 1), colors.HexColor("#B91C1C")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("TOPPADDING", (0, 1), (-1, 1), 6), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
    ]))
    story += [Paragraph("Attendance Summary", heading), summary]

    story.append(Paragraph(f"Present Students ({len(report.present)})", heading))
    if report.present:
        rows = [["S.No.", "Roll Number", "Student Name", "Status", "Marked At", "Method"]]
        rows += [[str(i), e.roll_number, cell(e.name), "PRESENT", _local(e.marked_at), _method(e)]
                 for i, e in enumerate(report.present, 1)]
        story.append(table(rows, [0.07, 0.13, 0.25, 0.11, 0.28, 0.16], colors.HexColor("#15803D")))
    else:
        story.append(Paragraph("No enrolled student has attendance recorded for this session.", body))

    story.append(Paragraph(f"Absent Students ({len(report.absent)})", heading))
    if report.absent:
        rows = [["S.No.", "Roll Number", "Student Name", "Status"]]
        rows += [[str(i), e.roll_number, cell(e.name), "ABSENT"] for i, e in enumerate(report.absent, 1)]
        story.append(table(rows, [0.08, 0.18, 0.54, 0.20], colors.HexColor("#B91C1C")))
    else:
        story.append(Paragraph("None." if report.total else "No students are enrolled in this classroom.", body))

    if report.not_enrolled:
        story.append(Paragraph(f"Attended but Not Enrolled ({len(report.not_enrolled)})", heading))
        story.append(Paragraph("Not counted in the totals above. Enroll them to include them in reports.", small))
        rows = [["S.No.", "Username", "Name", "Marked At", "Method"]]
        rows += [[str(i), e.username, cell(e.name), _local(e.marked_at), _method(e)]
                 for i, e in enumerate(report.not_enrolled, 1)]
        story.append(table(rows, [0.08, 0.18, 0.30, 0.26, 0.18], colors.HexColor("#64748B")))

    story += [Spacer(1, 10), Paragraph(
        "A card scan shows a registered card was tapped while the session was open; it does not prove who "
        "held the card.", small)]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(18 * mm, 10 * mm,
                          f"Generated {_local(report.generated_at)} · Session {session.id} · "
                          f"Generated by CampusOS AttendX")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=18 * mm, title=f"AttendX report · {session.title}",
                            author="CampusOS AttendX")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
