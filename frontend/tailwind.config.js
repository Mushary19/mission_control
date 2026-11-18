/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ['"Inter Variable"', "Inter", "ui-sans-serif", "system-ui", "sans-serif"] },
      fontSize: { base: ["14px", "20px"] },
      borderRadius: { lg: "8px", md: "6px", sm: "4px" },
      colors: { accent: { DEFAULT: "#4f46e5", soft: "#eef2ff" } },
      boxShadow: { none: "none" },
    },
  },
  plugins: [],
};
