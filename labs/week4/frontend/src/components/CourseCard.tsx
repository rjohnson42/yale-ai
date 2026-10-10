import type { Course } from "../api";

type CourseCardProps = {
  course: Course;
};

function facultyName(raw: string): string {
  const [last, first] = raw.split(",").map((part) => part.trim());
  if (first && last) return `${first} ${last}`;
  return raw || "Faculty to be announced";
}

function meeting(course: Course): string {
  const when = course.Daytimes.replace(/\s+/g, " ").trim();
  const room = course.Room.trim();
  if (when && room) return `${when} · ${room}`;
  return when || room || "Time to be announced";
}

export function CourseCard({ course }: CourseCardProps) {
  const description = course["Course Description"].replace(/\s+/g, " ").trim();
  return (
    <article className="card">
      <div className="card-kicker">
        <span className="code">{course["Course Number"]}</span>
        <span className="section">Section {course.Section || "—"}</span>
      </div>
      <h2>{course["Course Title"]}</h2>
      <p className="faculty">{facultyName(course["Faculty 1"])}</p>
      <p className="when">{meeting(course)}</p>
      {description ? <p className="blurb">{description}</p> : <p className="blurb quiet">No description on file.</p>}
      <div className="meta">
        {course["Course Category"] ? <span>{course["Course Category"]}</span> : null}
        {course["Course Session"] ? <span>{course["Course Session"]}</span> : null}
        {course.Units ? <span>{course.Units} units</span> : null}
      </div>
    </article>
  );
}
