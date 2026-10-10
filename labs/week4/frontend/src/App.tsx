import { useCallback, useEffect, useMemo, useState } from "react";
import { AuthError, fetchCourses, fetchMe, getToken, logout, type Course, type User } from "./api";
import { AuthScreen } from "./components/AuthScreen";
import { ChatPanel } from "./components/ChatPanel";
import { CourseCard } from "./components/CourseCard";

const FILTERS = ["All", "Core", "Finance", "Marketing", "Operations", "AI", "EMBA"];

function haystack(course: Course): string {
  return [
    course["Course Number"],
    course["Course Title"],
    course["Faculty 1"],
    course["Course Category"],
    course["Course Type"],
    course.Daytimes,
    course.Room,
    course["Course Description"],
  ]
    .join(" ")
    .toLowerCase();
}

function inFacet(course: Course, facet: string): boolean {
  if (facet === "All") return true;
  if (facet === "AI") {
    return matches(course, "AI") || course["Course Category"] === "Artificial Intelligence";
  }
  if (facet === "EMBA") {
    return course["Course Category"] === "EMBA" || course["Course Type"].toUpperCase().includes("EMBA");
  }
  return course["Course Category"] === facet;
}

function matches(course: Course, query: string): boolean {
  const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const text = haystack(course);
  return words.every((word) => {
    const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (new RegExp(`(?<![a-z0-9])${escaped}(?![a-z0-9])`).test(text)) return true;
    return word === "ai" && text.includes("artificial intelligence");
  });
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [sessionReady, setSessionReady] = useState(false);
  const [courses, setCourses] = useState<Course[]>([]);
  const [query, setQuery] = useState("");
  const [facet, setFacet] = useState("All");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      setSessionReady(true);
      return;
    }
    fetchMe()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setSessionReady(true));
  }, []);

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    fetchCourses()
      .then((rows) => {
        setCourses(rows);
        setError("");
      })
      .catch((reason: unknown) => {
        if (reason instanceof AuthError) {
          setUser(null);
          return;
        }
        setError(reason instanceof Error ? reason.message : "The catalog did not load.");
      })
      .finally(() => setLoading(false));
  }, [user]);

  const signOut = useCallback(async () => {
    await logout();
    setUser(null);
    setCourses([]);
    setChatOpen(false);
  }, []);

  const visible = useMemo(
    () => courses.filter((course) => inFacet(course, facet) && matches(course, query)),
    [courses, facet, query],
  );
  const uniqueCount = useMemo(
    () => new Set(courses.map((course) => course["Course Number"])).size,
    [courses],
  );
  const coreCount = useMemo(
    () =>
      new Set(
        courses
          .filter((course) => course["Course Category"] === "Core")
          .map((course) => course["Course Number"]),
      ).size,
    [courses],
  );

  if (!sessionReady) {
    return (
      <div className="gate">
        <div className="accent-bar" />
        <header className="topbar">
          <span className="brand">
            <img src="/yale-som-logo.svg" alt="Yale School of Management" />
          </span>
        </header>
      </div>
    );
  }

  if (!user) {
    return <AuthScreen onSignedIn={setUser} />;
  }

  return (
    <div className="page">
      <div className="accent-bar" />
      <header className="topbar">
        <a className="brand" href="https://som.yale.edu/" target="_blank" rel="noreferrer">
          <img src="/yale-som-logo.svg" alt="Yale School of Management" />
        </a>
        <span className="brand-rule" aria-hidden="true" />
        <span className="product">Course catalog</span>
        <div className="account">
          <span className="who">{user.name}</span>
          <button type="button" className="signout" onClick={() => void signOut()}>
            Sign out
          </button>
          <button type="button" className="ask" onClick={() => setChatOpen(true)}>
            Ask
          </button>
        </div>
      </header>

      <div className="workspace">
        <main>
          <div className="intro">
            <h1>Find a course</h1>
            <p>Search the Yale SOM shelf by number, faculty, day, or topic.</p>
          </div>

          <div className="stats">
            <div>
              <strong>{loading ? "—" : courses.length}</strong>
              <span>Sections</span>
            </div>
            <div>
              <strong>{loading ? "—" : uniqueCount}</strong>
              <span>Courses</span>
            </div>
            <div>
              <strong>{loading ? "—" : coreCount}</strong>
              <span>Core</span>
            </div>
          </div>

          <label className="search">
            <svg viewBox="0 0 20 20" aria-hidden="true">
              <circle cx="8.5" cy="8.5" r="5.5" />
              <path d="M12.5 12.5 17 17" />
            </svg>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search MGT 409, Zaman, Thursday, AI…"
              aria-label="Search the catalog"
            />
            {query ? (
              <button type="button" className="clear" onClick={() => setQuery("")}>
                Clear
              </button>
            ) : null}
          </label>

          <div className="toolbar">
            <div className="chips">
              {FILTERS.map((filter) => (
                <button
                  key={filter}
                  type="button"
                  className={facet === filter ? "chip on" : "chip"}
                  onClick={() => setFacet(filter)}
                >
                  {filter}
                </button>
              ))}
            </div>
            <p className="tally">
              {loading ? "Loading the catalog" : `${visible.length} sections`}
            </p>
          </div>

          {error ? <p className="banner">{error}</p> : null}
          {!loading && !error && visible.length === 0 ? (
            <p className="banner">No sections match that search.</p>
          ) : null}

          <section className="grid" aria-label="Courses">
            {loading
              ? Array.from({ length: 6 }, (_, index) => <div key={index} className="skeleton" />)
              : visible.map((course) => (
                  <CourseCard
                    key={`${course["Course Number"]}-${course.Section}-${course["Course Session"]}`}
                    course={course}
                  />
                ))}
          </section>
        </main>
        <ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} onSignOut={signOut} />
      </div>
    </div>
  );
}
