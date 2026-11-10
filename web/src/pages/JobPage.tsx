import { Link, useNavigate, useParams } from "react-router";
import { Header } from "../components/Header";
import { JobDetail } from "../components/JobDetail";

/** One job on its own page: used on phones and for direct links (Telegram's "Dashboard"). */
export function JobPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-bg">
      <Header q="" onSearch={(q) => navigate(q ? `/?q=${encodeURIComponent(q)}` : "/")} />
      <main className="mx-auto flex max-w-3xl flex-col gap-3 px-4 pt-4 pb-10">
        <Link to="/" className="self-start text-[13px] text-accent hover:underline">
          ← All jobs
        </Link>
        {Number.isInteger(id) && id > 0 ? (
          <JobDetail id={id} />
        ) : (
          <p className="text-muted">That job link isn't valid.</p>
        )}
      </main>
    </div>
  );
}
