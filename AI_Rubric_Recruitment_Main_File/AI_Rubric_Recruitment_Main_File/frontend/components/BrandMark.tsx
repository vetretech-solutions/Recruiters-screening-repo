import Link from "next/link";

type BrandMarkProps = {
  href?: string;
  size?: "sm" | "md";
};

export default function BrandMark({ href = "/", size = "md" }: BrandMarkProps) {
  const content = (
    <>
      <div className={`brand-mark brand-mark--${size}`} aria-hidden="true">
        AR
      </div>
      <span className={`brand-name brand-name--${size}`}>AI Recruiter</span>
    </>
  );

  if (href) {
    return (
      <Link href={href} className="brand-block">
        {content}
      </Link>
    );
  }

  return <div className="brand-block">{content}</div>;
}
