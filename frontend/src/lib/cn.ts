/**
 * 合并 CSS 类名的小工具。全站到处都在用。
 *
 * 解决两个问题：
 *   clsx    —— 支持条件写法：cn("btn", isActive && "btn-active")
 *              条件为假时那一项会被自动丢掉，不会留下 "false"
 *   twMerge —— 解决 Tailwind 类名冲突：cn("p-2", "p-4") → "p-4"
 *              没有它的话两个 padding 都会保留，最终哪个生效看 CSS 顺序，
 *              结果不可预测
 */

import clsx, { type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
