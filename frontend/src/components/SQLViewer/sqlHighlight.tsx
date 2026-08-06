import type { JSX } from "react";
import { cn } from "@/lib/utils";

const SQL_KEYWORDS = new Set([
  "SELECT", "FROM", "WHERE", "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "OUTER", "ON", "GROUP",
  "BY", "ORDER", "HAVING", "LIMIT", "OFFSET", "AS", "AND", "OR", "NOT", "NULL", "IS", "IN",
  "EXISTS", "DISTINCT", "UNION", "ALL", "CASE", "WHEN", "THEN", "ELSE", "END", "WITH", "INSERT",
  "INTO", "VALUES", "UPDATE", "SET", "DELETE", "CREATE", "TABLE", "ASC", "DESC", "BETWEEN",
  "LIKE", "COUNT", "SUM", "AVG", "MIN", "MAX", "COALESCE", "CAST", "OVER", "PARTITION", "ROW_NUMBER",
]);

type TokenType = "keyword" | "string" | "number" | "comment" | "plain";

interface Token {
  text: string;
  type: TokenType;
}

const TOKEN_PATTERN = /(--[^\n]*)|('(?:[^']|'')*')|(\b\d+\.?\d*\b)|([a-zA-Z_][a-zA-Z0-9_]*)/g;

function tokenize(sql: string): Token[] {
  const tokens: Token[] = [];
  let lastIndex = 0;
  for (const match of sql.matchAll(TOKEN_PATTERN)) {
    const index = match.index;
    if (index > lastIndex) {
      tokens.push({ text: sql.slice(lastIndex, index), type: "plain" });
    }
    const [full, comment, str, num, word] = match;
    if (comment !== undefined) tokens.push({ text: comment, type: "comment" });
    else if (str !== undefined) tokens.push({ text: str, type: "string" });
    else if (num !== undefined) tokens.push({ text: num, type: "number" });
    else if (word !== undefined) {
      tokens.push({ text: word, type: SQL_KEYWORDS.has(word.toUpperCase()) ? "keyword" : "plain" });
    }
    lastIndex = index + full.length;
  }
  if (lastIndex < sql.length) tokens.push({ text: sql.slice(lastIndex), type: "plain" });
  return tokens;
}

const TOKEN_CLASS: Record<TokenType, string> = {
  keyword: "text-primary font-semibold",
  string: "text-success",
  number: "text-warning",
  comment: "italic text-muted-foreground",
  plain: "",
};

/** A small, dependency-free SQL syntax highlighter -- keywords, strings, numbers, and line
 * comments only. Not a parser: purely cosmetic token coloring for readability.
 */
export function SqlHighlight({ sql, className }: { sql: string; className?: string }): JSX.Element {
  const tokens = tokenize(sql);
  return (
    <code className={cn("font-mono text-sm leading-relaxed", className)}>
      {tokens.map((token, index) => (
        <span key={index} className={TOKEN_CLASS[token.type]}>
          {token.text}
        </span>
      ))}
    </code>
  );
}
