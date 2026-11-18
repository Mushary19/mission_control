/** @type {import('tailwindcss').Config} */
// Type scale (rem, so it follows the 18px root set in index.css). Use these tokens, never text-[Npx].
// The smallest text anywhere is `sm` (0.875rem = 15.75px); text-xs does not exist on purpose.
//   sm      table cells, labels, badges, timestamps, helper text
//   base    body text (line-height 1.6)
//   card    card titles, table headers (weight 500)
//   section section headings (weight 600)
//   title   page titles (weight 600)
//   stat    stat tile numbers (weight 600)
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    fontSize: {
      sm: ["0.875rem", "1.25rem"],
      base: ["0.9375rem", "1.6"],
      card: ["0.9375rem", { lineHeight: "1.5rem", fontWeight: "500" }],
      section: ["1.125rem", { lineHeight: "1.75rem", fontWeight: "600" }],
      title: ["1.5rem", { lineHeight: "2rem", fontWeight: "600" }],
      stat: ["1.75rem", { lineHeight: "2.25rem", fontWeight: "600" }],
    },
    extend: {
      fontFamily: { sans: ['"Inter Variable"', "Inter", "ui-sans-serif", "system-ui", "sans-serif"] },
      // Fixed layout sizes in px (they must not grow with the root font).
      spacing: { sidebar: "264px", bar: "64px", nav: "44px", page: "40px", icon: "20px" },
      maxWidth: { content: "1600px" },
      borderRadius: { lg: "8px", md: "6px", sm: "4px" },
      colors: { accent: { DEFAULT: "#4f46e5", soft: "#eef2ff" } },
      boxShadow: { none: "none" },
    },
  },
  plugins: [],
};
