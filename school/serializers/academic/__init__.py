from .classroom  import ClassRoomSerializer
from .term       import TermSerializer
from .student    import StudentSerializer
from .attendance import AttendanceSerializer, BulkAttendanceSerializer
from .assignment import AssignmentSerializer
from .report     import SubjectScoreSerializer, AcademicReportSerializer, AcademicReportListSerializer

__all__ = [
    "ClassRoomSerializer",
    "TermSerializer",
    "StudentSerializer",
    "AttendanceSerializer",
    "BulkAttendanceSerializer",
    "AssignmentSerializer",
    "SubjectScoreSerializer",
    "AcademicReportSerializer",
    "AcademicReportListSerializer",
]