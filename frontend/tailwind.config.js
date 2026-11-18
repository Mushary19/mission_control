/** @type {import('tailwindcss').Config} */
// Type scale. Use these tokens, never one-off text-[Npx] classes. Nothing is smaller than 12px.
//   micro   12px  floor: raw JSON / file references only
//   xs      13px  small labels, badges, timestamps, helper text
//   sm      14px  table cells, inputs, buttons
//   base    15px  body text (line-height 1.6)
//   card    15px  card titles, table headers (weight 500)
//   section 18px  section headings (weight 600)
//   title   24px  page titles (weight 600)
//   stat    28px  stat tile numbers (weight 600)
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ['"Inter Variable"', "Inter", "ui-sans-serif", "system-ui", "sans-serif"] },
      fontSize: {
        micro: ["12px", "18px"],
        xs: ["13px", "20px"],
        sm: ["14px", "20px"],
        base: ["15px", "1.6"],
        card: ["15px", { lineHeight: "24px", fontWeight: "500" }],
        section: ["18px", { lineHeight: "28px", fontWeight: "600" }],
        title: ["24px", { lineHeight: "32px", fontWeight: "600" }],
        stat: ["28px", { lineHeight: "36px", fontWeight: "600" }],
      },
      spacing: { sidebar: "248px", bar: "56px" },
      maxWidth: { content: "1280px" },
      borderRadius: { lg: "8px", md: "6px", sm: "4px" },
      colors: { accent: { DEFAULT: "#4f46e5", soft: "#eef2ff" } },
      boxShadow: { none: "none" },
    },
  },
  plugins: [],
};
