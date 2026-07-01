from .classroom  import ClassRoomViewSet
from .term       import TermViewSet
from .student    import StudentViewSet
from .attendance import AttendanceViewSet
from .assignment import AssignmentViewSet
from .report     import AcademicReportViewSet

__all__ = [
    "ClassRoomViewSet",
    "TermViewSet",
    "StudentViewSet",
    "AttendanceViewSet",
    "AssignmentViewSet",
    "AcademicReportViewSet",
]