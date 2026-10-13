export type SourceRef = {
  document_id: string;
  version_id: string;
  locator_type: string;
  locator: number;
  quote: string;
};
export type Card = {
  id?: string;
  front: string;
  back: string;
  course_id: string | null;
  topic: string;
  sources: SourceRef[];
  due_at?: string;
  interval_days?: number;
};
export type Question = {
  id?: string;
  kind: "single" | "multiple" | "short" | "math";
  prompt: string;
  options: string[];
  correct_indices: number[];
  answer: string;
  explanation: string;
  topic: string;
  sources: SourceRef[];
};
export type Quiz = {
  id?: string;
  title: string;
  course_id: string | null;
  questions: Question[];
};
export type Answer = {
  question_id: string;
  selected: number[];
  text: string;
  self_correct: boolean | null;
};
export type Attempt = {
  id: string;
  quiz_id: string;
  quiz_title: string;
  score: number;
  total: number;
  created_at: string;
  answers: (Answer & { correct: boolean; question: Question })[];
};
export const kindLabels = {
  single: "单选题",
  multiple: "多选题",
  short: "简答题",
  math: "数学题",
};
export function blankQuestion(): Question {
  return {
    kind: "single",
    prompt: "",
    options: ["", ""],
    correct_indices: [0],
    answer: "",
    explanation: "",
    topic: "",
    sources: [],
  };
}
