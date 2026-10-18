import type { Metadata } from "next";
import { AskClient } from "./ask-client";

export const metadata: Metadata = { title: "Ask" };

export default function Page() {
  return <AskClient />;
}
