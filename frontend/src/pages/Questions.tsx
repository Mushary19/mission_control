import { ErrorNote, Loading, PageHeader } from "@/components/common";
import { QuestionCard } from "@/components/Cards";
import { useAllProcesses, useFeedback } from "@/lib/api";

export default function Questions() {
  const procs = useAllProcesses();
  const fb = useFeedback();
  const err = procs.find((p) => p.error)?.error;
  if (err) return <ErrorNote error={err} />;
  if (procs.some((p) => !p.data)) return <Loading rows={8} />;
  const answered = new Set(fb.data?.items.filter((f) => f.target === "open_question").map((f) => f.question_id));
  const total = procs.reduce((n, p) => n + p.data!.open_questions.length, 0);
  return (
    <>
      <PageHeader title="Questions for staff" subtitle={`Where the data is thin or shows two ways of working. ${answered.size} of ${total} answered.`} />
      <div className="space-y-8">
        {procs.map((p) => (
          <section key={p.data!.process}>
            <h2 className="mb-2 text-[13px] font-semibold">{p.data!.label}</h2>
            <div className="grid grid-cols-2 gap-3">{p.data!.open_questions.map((q) => <QuestionCard key={q.id} q={q} feedback={fb.data?.items} />)}</div>
          </section>
        ))}
      </div>
    </>
  );
}
