import type { Metadata } from "next";
import { DayOneClient } from "./day-one-client";

export const metadata: Metadata = { title: "Day One" };

export default function Page() {
  return <DayOneClient />;
}
