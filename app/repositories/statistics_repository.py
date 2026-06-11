from sqlalchemy.orm import Session

from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.question_repository import QuestionRepository
from app.repositories.unanswered_repository import UnansweredRepository


class StatisticsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.knowledge_repo = KnowledgeRepository(session)
        self.question_repo = QuestionRepository(session)
        self.unanswered_repo = UnansweredRepository(session)
        self.feedback_repo = FeedbackRepository(session)

    def get_dashboard_counts(self) -> dict:
        total_questions = self.question_repo.count_logs()
        matched_questions = self.question_repo.count_matched()
        missed_questions = max(total_questions - matched_questions, 0)

        if total_questions > 0:
            match_rate = round(matched_questions / total_questions, 3)
            miss_rate = round(missed_questions / total_questions, 3)
        else:
            match_rate = 0.0
            miss_rate = 0.0

        useful_feedback_count = self.feedback_repo.count_by_type("useful")
        useless_feedback_count = self.feedback_repo.count_by_type("useless")
        need_human_feedback_count = self.feedback_repo.count_by_type("need_human")
        feedback_total = useful_feedback_count + useless_feedback_count + need_human_feedback_count

        satisfaction_denominator = useful_feedback_count + useless_feedback_count
        satisfaction_rate = (
            round(useful_feedback_count / satisfaction_denominator, 3)
            if satisfaction_denominator > 0
            else 0.0
        )

        return {
            "total_questions": total_questions,
            "matched_questions": matched_questions,
            "missed_questions": missed_questions,
            "match_rate": match_rate,
            "miss_rate": miss_rate,
            "feedback_total": feedback_total,
            "useful_feedback_count": useful_feedback_count,
            "useless_feedback_count": useless_feedback_count,
            "need_human_feedback_count": need_human_feedback_count,
            "satisfaction_rate": satisfaction_rate,
            "total_knowledge_cards": self.knowledge_repo.count_cards(),
            "approved_knowledge_cards": self.knowledge_repo.count_approved(),
            "pending_knowledge_cards": self.knowledge_repo.count_pending_audit(),
            "unanswered_questions": self.unanswered_repo.count_questions(),
            "top_unanswered_questions": self.unanswered_repo.top_unanswered(limit=10),
            "top_negative_feedback_questions": self.feedback_repo.top_negative_feedback(limit=10),
        }
