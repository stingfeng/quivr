import { redirect } from "next/navigation";
import Features from "./Features";
import Hero from "./Hero";

export default function HomePage() {
  if (process.env.NEXT_PUBLIC_ENV === "local") {
    redirect("/upload");
  }
  redirect("/chat");

  return (
    <main className="">
      <Hero />
      <Features />
    </main>
  );
}
