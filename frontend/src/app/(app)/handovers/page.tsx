import type { Metadata } from "next";
import { HandoversClient } from "./handovers-client";

export const metadata: Metadata = { title: "Handovers" };

export default function Page() {
  return <HandoversClient />;
}
