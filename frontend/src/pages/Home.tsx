import { Link } from "react-router-dom";
import { Card } from "../components/ui";

const SERVICES = [
  ["Resume analysis", "Skills, strengths, gaps and ATS advice from your resume."],
  ["Job description analysis", "Mandatory, preferred and optional requirements, extracted."],
  ["Resume and job match", "A transparent, explainable match estimate."],
  ["Skill gap analysis", "What is missing, how severe, and a study timeline."],
  ["Resume optimisation", "Edits that never invent skills or experience."],
];

export default function Home() {
  return (
    <>
      <h1 className="mb-2 text-3xl font-bold">AI Career Coach</h1>
      <p className="mb-4 text-gray-700">
        Five career services work without an account. Register for saved history, learning roadmaps (7, 15 or 60
        days), assessments, certificates, a portfolio and the AI coach.
      </p>
      <Link to="/analyze" className="mb-6 inline-block rounded bg-blue-600 px-4 py-2 font-medium text-white">
        Try it now, no sign-in
      </Link>
      <div className="grid gap-3 md:grid-cols-2">
        {SERVICES.map(([t, d]) => (
          <Card key={t} title={t}>
            <p className="text-sm text-gray-700">{d}</p>
          </Card>
        ))}
      </div>
    </>
  );
}
