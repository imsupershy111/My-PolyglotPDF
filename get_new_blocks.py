# NHIỆM VỤ: Phân tích cấu trúc trang PDF (PyMuPDF), trích xuất từng khối văn bản (boxes), gom nhóm các từ và dòng để bóc tách toạ độ chính xác cho việc chèn dịch.

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import fitz  # Module của PyMuPDF tên là fitz
import math
import datetime
import unicodedata
from collections import defaultdict

# Danh sách các font chứa ký hiệu Toán học để né việc dịch
MATH_FONTS_SET = {
    "CMMI", "CMSY", "CMEX", "CMMI5", "CMMI6", "CMMI7", "CMMI8", "CMMI9", "CMMI10",
    "CMSY5", "CMSY6", "CMSY7", "CMSY8", "CMSY9", "CMSY10",
    "CMEX5", "CMEX6", "CMEX7", "CMEX8", "CMEX9", "CMEX10",
    "MSAM", "MSBM", "EUFM", "EUSM", "TXMI", "TXSY", "PXMI", "PXSY",
    "CambriaMath", "AsanaMath", "STIXMath", "XitsMath", "Latin Modern Math",
    "Neo Euler", 'MTMI', 'MTSYN', 'TimesNewRomanPSMT'
}

def snap_angle_func(raw_angle):
    """
    Làm tròn góc quay về các mốc 0, 90, 180, 270, 360 độ.
    Chuyển đổi góc ngược: 270->90, 90->270, 360->0
    """
    possible_angles = [0, 90, 180, 270, 360]
    normalized_angle = raw_angle % 360
    closest_angle = min(possible_angles, key=lambda x: abs(x - normalized_angle))
    angle_mapping = {
        270: 90,
        90: 270,
        360: 0
    }
    return angle_mapping.get(closest_angle, closest_angle)

def horizontal_merge(lines_data, max_horizontal_gap=10, max_y_diff=5, check_font_size=False, check_font_name=False, check_font_color=False, bold_max_horizontal_gap=20):
    """Gộp các khối chữ theo phương ngang nếu chúng nằm kề sát nhau."""
    if not lines_data:
        return []

    merged = []
    i = 0
    n = len(lines_data)
    while i < n:
        line = lines_data[i]
        if not merged:
            merged.append(line)
            i += 1
            continue

        prev_line = merged[-1]
        x0, y0, x1, y1 = line["line_bbox"]
        px0, py0, px1, py1 = prev_line["line_bbox"]
        curr_font_size = line["font_size"] if line["font_size"] else 10
        prev_font_size = prev_line["font_size"] if prev_line["font_size"] else 10
        avg_font_size = (curr_font_size+prev_font_size)/2
        
        # (1) Nếu bbox giao nhau rõ ràng -> gộp thẳng
        overlap_y = (y0 <= py1) and (py0 <= y1) and (abs(y0-py1) > avg_font_size/5)
        overlap_x = (x0 <= px1) and (px0 <= x1)
        merged_this_round = False

        if overlap_x and overlap_y:
            prev_line["text"] = prev_line["text"].rstrip() + " " + line["text"].lstrip()
            new_x0 = min(px0, x0)
            new_y0 = min(py0, y0)
            new_x1 = max(px1, x1)
            new_y1 = max(py1, y1)
            prev_line["line_bbox"] = (new_x0, new_y0, new_x1, new_y1)
            prev_line["total_bold_chars"] += line["total_bold_chars"]
            prev_line["total_nonbold_chars"] += line["total_nonbold_chars"]
            prev_line["font_bold"] = prev_line["total_bold_chars"] > prev_line["total_nonbold_chars"]
            prev_line["font_names"].extend(line["font_names"])
            prev_line["font_names"] = list(set(prev_line["font_names"]))
            merged_this_round = True
        else:
            # (2) Tinh chỉnh điều kiện gộp dựa trên layout
            same_block = (line["block_index"] == prev_line["block_index"])
            same_font_size_flag = (line["font_size"] == prev_line["font_size"])
            same_font_name_flag = (line["font_name"] == prev_line["font_name"])

            color_diff_val = 0
            if line["font_color"] is not None and prev_line["font_color"] is not None:
                color_diff_val = abs(line["font_color"] - prev_line["font_color"])
            same_font_color_flag = (color_diff_val <= 50)

            if not check_font_size: same_font_size_flag = True
            if not check_font_name: same_font_name_flag = True
            if not check_font_color: same_font_color_flag = True

            effective_max_gap = avg_font_size
            same_horizontal_line = abs(py1-y1) < avg_font_size/5 and abs(py0-y0) < avg_font_size/5
            horizontal_gap = x0 - px1
            close_enough = (0 <= horizontal_gap < effective_max_gap)

            if (same_block and same_font_size_flag and same_font_name_flag and same_font_color_flag and same_horizontal_line and close_enough):
                prev_line["text"] = prev_line["text"].rstrip() + " " + line["text"].lstrip()
                new_x0 = min(px0, x0)
                new_y0 = min(py0, y0)
                new_x1 = max(px1, x1)
                new_y1 = max(py1, y1)
                prev_line["line_bbox"] = (new_x0, new_y0, new_x1, new_y1)
                prev_line["total_bold_chars"] += line["total_bold_chars"]
                prev_line["total_nonbold_chars"] += line["total_nonbold_chars"]
                prev_line["font_bold"] = prev_line["total_bold_chars"] > prev_line["total_nonbold_chars"]
                prev_line["font_names"].extend(line["font_names"])
                prev_line["font_names"] = list(set(prev_line["font_names"]))
                merged_this_round = True

        if merged_this_round:
            i += 1
            continue
        else:
            merged.append(line)
            i += 1

    return merged

def merge_lines(lines_data, check_font_size=False, check_font_name=True, check_font_color=True, check_same_block=True):
    """Gộp các đoạn chữ xuống dòng (vertical merge) trong cùng một đoạn văn."""
    merged = []
    i = 0
    n = len(lines_data)
    while i < n:
        line = lines_data[i]
        if not merged:
            merged.append(line)
            i += 1
            continue

        prev_line = merged[-1]
        x0, y0, x1, y1 = line["line_bbox"]
        px0, py0, px1, py1 = prev_line["line_bbox"]
        current_width = (x1 - x0)
        prev_width = (px1 - px0)
        prev_indent = prev_line['indent']

        same_block = (line["block_index"] == prev_line["block_index"]) if check_same_block else True
        no_end_indent = prev_line["end_indent"] == 0

        # Cờ font size
        if check_font_size:
            if line["font_size"] is not None and prev_line["font_size"] is not None:
                font_size_diff = abs(line["font_size"] - prev_line["font_size"])
                same_font_size_flag = (font_size_diff <= 0.6)
            else:
                same_font_size_flag = True
        else:
            same_font_size_flag = True

        # Cờ font name
        same_font_name_flag = (line["font_name"] == prev_line["font_name"]) if check_font_name else True

        # Cờ font color
        color_diff_val = 0
        if line["font_color"] is not None and prev_line["font_color"] is not None:
            color_diff_val = abs(line["font_color"] - prev_line["font_color"])
        same_font_color_flag = (color_diff_val <= 50) if check_font_color else True

        # Threshold động
        curr_font_size = line["font_size"] if line["font_size"] else 10
        prev_font_size = prev_line["font_size"] if prev_line["font_size"] else 10
        max_horizontal_gap = (curr_font_size + prev_font_size) / 2.0
        margin_in_middle = max_horizontal_gap / 1.5
        max_x_distance = max_horizontal_gap * 8

        # Khe hở trục Y và X
        y_distance = (y0 - py1)
        y_distance_small = (abs(y_distance) < max_horizontal_gap/1.3)
        horizontal_distance = abs(x0 - px0)
        x_distance_small = (horizontal_distance < max_x_distance)

        avg_font_size = (curr_font_size+prev_font_size)/2
        overlap_y = (y0 <= py1) and (py0 <= y1) and (abs(y0-py1) > avg_font_size/5)
        overlap_x = (x0 <= px1) and (px0 <= x1)

        # Bộ quy tắc (heuristics) để xác định xem có nên gộp dòng hay không
        condition_1 = (same_block and same_font_size_flag and same_font_name_flag and same_font_color_flag and y_distance_small and (x0 >= px0 + margin_in_middle) and (x1 <= px1 - margin_in_middle) and no_end_indent and abs(abs(x0-px0) - abs(x1-px1)) < max_horizontal_gap)
        condition_2 = (same_block and y_distance_small and x_distance_small and (abs(px0 - x0) < margin_in_middle) and no_end_indent and ((current_width - prev_width) < max_horizontal_gap*2))
        condition_3 = (same_block and y_distance_small and same_font_size_flag and same_font_name_flag and same_font_color_flag and x_distance_small and no_end_indent)
        tolerance = max_horizontal_gap / 2
        condition_4 = (same_block and (x0 >= px0 - tolerance) and (y0 >= py0 - tolerance) and (x1 <= px1 + tolerance) and (y1 <= py1 + tolerance) and no_end_indent)
        condition_5 = (same_block and y_distance_small and x_distance_small and (px0-x0) < max_horizontal_gap * 2 and no_end_indent and (abs(current_width-prev_width) < max_x_distance))

        merged_this_round = False

        if overlap_x and overlap_y:
            prev_line["text"] = prev_line["text"].rstrip() + " " + line["text"].lstrip()
            indent_val = prev_indent if prev_indent else ((px0 - x0) if (px0 > x0) else 0)
            end_indent_val = abs(px1 - x1) if (px1 > x1 and abs(px1 - x1) > max_horizontal_gap) else 0
            
            merged[-1]["end_indent"] = end_indent_val
            new_x0, new_y0 = min(px0, x0), min(py0, y0)
            new_x1, new_y1 = max(px1, x1), max(py1, y1)
            prev_line["line_bbox"] = (new_x0, new_y0, new_x1, new_y1)
            prev_line["total_bold_chars"] += line["total_bold_chars"]
            prev_line["total_nonbold_chars"] += line["total_nonbold_chars"]
            prev_line["font_bold"] = prev_line["total_bold_chars"] > prev_line["total_nonbold_chars"]
            prev_line["font_names"].extend(line["font_names"])
            prev_line["font_names"] = list(set(prev_line["font_names"]))
            merged[-1]["indent"] = indent_val
            merged_this_round = True

        elif condition_1:
            merged[-1]["text"] = prev_line["text"].rstrip() + " " + line["text"].lstrip()
            new_x0, new_y0 = min(px0, x0), min(py0, y0)
            new_x1, new_y1 = max(px1, x1), max(py1, y1)
            merged[-1]["line_bbox"] = (new_x0, new_y0, new_x1, new_y1)
            merged[-1]["total_bold_chars"] += line["total_bold_chars"]
            merged[-1]["total_nonbold_chars"] += line["total_nonbold_chars"]
            merged[-1]["font_bold"] = merged[-1]["total_bold_chars"] > merged[-1]["total_nonbold_chars"]
            merged[-1]["font_names"].extend(line["font_names"])
            merged[-1]["font_names"] = list(set(merged[-1]["font_names"]))
            if line["font_size"] is not None and line["font_size"] > margin_in_middle * 2:
                merged[-1]["type"] = "title"
            merged_this_round = True

        elif condition_2:
            indent_val = prev_indent if prev_indent else ((px0 - x0) if (px0 > x0) else 0)
            merged[-1]["indent"] = indent_val
            end_indent_val = abs(px1 - x1) if (px1 > x1 and abs(px1 - x1) > max_horizontal_gap) else 0
            merged[-1]["end_indent"] = end_indent_val
            merged[-1]["text"] = prev_line["text"].rstrip() + " " + line["text"].lstrip()
            new_x0, new_y0 = min(px0, x0), min(py0, y0)
            new_x1, new_y1 = max(px1, x1), max(py1, y1)
            merged[-1]["line_bbox"] = (new_x0, new_y0, new_x1, new_y1)
            merged[-1]["total_bold_chars"] += line["total_bold_chars"]
            merged[-1]["total_nonbold_chars"] += line["total_nonbold_chars"]
            merged[-1]["font_bold"] = merged[-1]["total_bold_chars"] > merged[-1]["total_nonbold_chars"]
            merged[-1]["font_names"].extend(line["font_names"])
            merged[-1]["font_names"] = list(set(merged[-1]["font_names"]))
            merged_this_round = True

        elif condition_5:
            indent_val = prev_line['indent'] if prev_line['indent'] else ((px0 - x0) if (px0 > x0) else 0)
            merged[-1]["indent"] = indent_val
            end_indent_val = abs(px1 - x1) if (px1 > x1 and abs(px1 - x1) > max_horizontal_gap) else 0
            merged[-1]["end_indent"] = end_indent_val
            merged[-1]["text"] = prev_line["text"].rstrip() + " " + line["text"].lstrip()
            new_x0, new_y0 = min(px0, x0), min(py0, y0)
            new_x1, new_y1 = max(px1, x1), max(py1, y1)
            merged[-1]["line_bbox"] = (new_x0, new_y0, new_x1, new_y1)
            merged[-1]["total_bold_chars"] += line["total_bold_chars"]
            merged[-1]["total_nonbold_chars"] += line["total_nonbold_chars"]
            merged[-1]["font_bold"] = merged[-1]["total_bold_chars"] > merged[-1]["total_nonbold_chars"]
            merged[-1]["font_names"].extend(line["font_names"])
            merged[-1]["font_names"] = list(set(merged[-1]["font_names"]))
            merged_this_round = True

        elif condition_3:
            if (x1 - px1) > max_x_distance:
                merged.append(line)
                i += 1
                continue
            width_diff = abs(current_width - prev_width)
            if width_diff <= margin_in_middle / 2.0:
                merged_text = prev_line["text"].rstrip() + " " + line["text"].lstrip()
                indent_val = (x0 - px0) if (x0 > px0 and (x0 - px0) > (max_horizontal_gap / 2)) else 0
                merged[-1]["indent"] = indent_val
                end_indent_val = abs(px1 - x1) if (px1 > x1 and abs(px1 - x1) > max_horizontal_gap) else 0
                merged[-1]["end_indent"] = end_indent_val
                prev_line["text"] = merged_text
                new_x0, new_y0 = min(px0, x0), min(py0, y0)
                new_x1, new_y1 = max(px1, x1), max(py1, y1)
                prev_line["line_bbox"] = (new_x0, new_y0, new_x1, new_y1)
                prev_line["total_bold_chars"] += line["total_bold_chars"]
                prev_line["total_nonbold_chars"] += line["total_nonbold_chars"]
                prev_line["font_bold"] = prev_line["total_bold_chars"] > prev_line["total_nonbold_chars"]
                prev_line["font_names"].extend(line["font_names"])
                prev_line["font_names"] = list(set(prev_line["font_names"]))
                merged_this_round = True
            else:
                if (prev_width < current_width) and (px0 > x0):
                    indent_val = (x0 - px0) if (x0 > px0 and (x0 - px0) > (max_horizontal_gap / 2)) else 0
                    merged[-1]["indent"] = indent_val
                    end_indent_val = abs(px1 - x1) if (px1 > x1 and abs(px1 - x1) > max_horizontal_gap) else 0
                    merged[-1]["end_indent"] = end_indent_val
                    merged_text = prev_line["text"].rstrip() + " " + line["text"].lstrip()
                    prev_line["text"] = merged_text
                    new_x0, new_y0 = min(px0, x0), min(py0, y0)
                    new_x1, new_y1 = max(px1, x1), max(py1, y1)
                    prev_line["line_bbox"] = (new_x0, new_y0, new_x1, new_y1)
                    prev_line["total_bold_chars"] += line["total_bold_chars"]
                    prev_line["total_nonbold_chars"] += line["total_nonbold_chars"]
                    prev_line["font_bold"] = prev_line["total_bold_chars"] > prev_line["total_nonbold_chars"]
                    prev_line["font_names"].extend(line["font_names"])
                    prev_line["font_names"] = list(set(prev_line["font_names"]))
                    merged_this_round = True
                elif (current_width < prev_width) and (x0 >= px0 + 2):
                    merged.append(line)
                    i += 1
                    continue
                else:
                    if prev_width < current_width:
                        indent_val = (x0 - px0) if (x0 > px0 and (x0 - px0) > (max_horizontal_gap / 2)) else 0
                        merged[-1]["indent"] = indent_val
                        end_indent_val = abs(px1 - x1) if (px1 > x1 and abs(px1 - x1) > max_horizontal_gap) else 0
                        merged[-1]["end_indent"] = end_indent_val
                        merged_text = prev_line["text"].rstrip() + " " + line["text"].lstrip()
                        prev_line["text"] = merged_text
                        new_x0, new_y0 = min(px0, x0), min(py0, y0)
                        new_x1, new_y1 = max(px1, x1), max(py1, y1)
                        prev_line["line_bbox"] = (new_x0, new_y0, new_x1, new_y1)
                        prev_line["total_bold_chars"] += line["total_bold_chars"]
                        prev_line["total_nonbold_chars"] += line["total_nonbold_chars"]
                        prev_line["font_bold"] = prev_line["total_bold_chars"] > prev_line["total_nonbold_chars"]
                        prev_line["font_names"].extend(line["font_names"])
                        prev_line["font_names"] = list(set(prev_line["font_names"]))
                        merged_this_round = True

        elif condition_4:
            merged[-1]["text"] = prev_line["text"].rstrip() + " " + line["text"].lstrip()
            new_x0, new_y0 = min(px0, x0), min(py0, y0)
            new_x1, new_y1 = max(px1, x1), max(py1, y1)
            indent_val = (x0 - px0) if (x0 > px0 and (x0 - px0) > (max_horizontal_gap / 2) )else 0
            merged[-1]["indent"] = indent_val
            end_indent_val = abs(px1 - x1) if (px1 > x1 and abs(px1 - x1) > max_horizontal_gap) else 0
            merged[-1]["end_indent"] = end_indent_val
            merged[-1]["line_bbox"] = (new_x0, new_y0, new_x1, new_y1)
            merged[-1]["total_bold_chars"] += line["total_bold_chars"]
            merged[-1]["total_nonbold_chars"] += line["total_nonbold_chars"]
            merged[-1]["font_bold"] = merged[-1]["total_bold_chars"] > merged[-1]["total_nonbold_chars"]
            merged[-1]["font_names"].extend(line["font_names"])
            merged[-1]["font_names"] = list(set(merged[-1]["font_names"]))
            merged_this_round = True

        if merged_this_round:
            i += 1
            continue
        else:
            merged.append(line)
            i += 1

    return merged

def is_math(font_info_list, text_len, text, font_size):
    """
    Kiểm tra xem text có phải là công thức toán học hay không.
    Trả về True nếu là Toán, 'abandon' nếu là ký tự vô nghĩa quá ngắn, False nếu là text thường.
    """
    text_length_nospaces = len(text.replace(" ", ""))

    if text_length_nospaces < font_size * 1.0:
        font_set = set(font_info_list)
        if font_set & MATH_FONTS_SET:
            return True

    if text_len < 1.5 * font_size:
        all_special_chars = True
        stripped_text = text.strip()
        for ch in stripped_text:
            cat = unicodedata.category(ch)
            if not (cat == 'Nd' or cat.startswith('P') or cat.startswith('S') or cat.startswith('Z')):
                all_special_chars = False
                break

        if all_special_chars:
            return "abandon"
        return False

    return False

def merge_adjacent_math_lines(lines):
    """Gộp các dòng toán học liền kề nhau để tránh việc phân mảnh công thức."""
    if not lines: return []

    def get_font_size(line):
        return line["font_size"] if line["font_size"] else 10

    def can_merge(prev_line, curr_line):
        px0, py0, px1, py1 = prev_line["line_bbox"]
        cx0, cy0, cx1, cy1 = curr_line["line_bbox"]

        x_distance = min(abs(px0 - cx1), abs(cx0 - px1))
        y_distance = min(abs(py0 - cy1), abs(cy0 - py1))
        x_distance_overlap = min(abs(px0 - cx0), abs(cx1 - px1))

        prev_is_math = (prev_line["type"] == "math")
        curr_is_math = (curr_line["type"] == "math")
        prev_len = prev_line["total_bold_chars"] + prev_line["total_nonbold_chars"]
        curr_len = curr_line["total_bold_chars"] + curr_line["total_nonbold_chars"]

        fs_p, fs_c = get_font_size(prev_line), get_font_size(curr_line)
        max_horizontal_gap = (fs_p + fs_c) / 2.0 

        cond_math_both = (prev_is_math and curr_is_math and ((x_distance < 5 * max_horizontal_gap and y_distance < 3 * max_horizontal_gap) or (x_distance_overlap < 5 * max_horizontal_gap and y_distance < 3 * max_horizontal_gap)))
        cond_one_math_prev = (prev_is_math and not curr_is_math and (curr_len < max_horizontal_gap) and (x_distance < 2 * max_horizontal_gap) and (y_distance < 1.5 * max_horizontal_gap))
        cond_one_math_curr = (not prev_is_math and curr_is_math and (prev_len < max_horizontal_gap) and (x_distance < 2 * max_horizontal_gap) and (y_distance < 1.5 * max_horizontal_gap))

        if cond_math_both: return (True, "BOTH_MATH")
        elif cond_one_math_prev: return (True, "ONE_MATH_PREV")
        elif cond_one_math_curr: return (True, "ONE_MATH_CURR")
        else: return (False, None)

    def do_merge(prev_line, curr_line, merge_type):
        if merge_type == "ONE_MATH_CURR": prev_line["type"] = "math"
        elif merge_type == "ONE_MATH_PREV": curr_line["type"] = "math"

        prev_line["text"] = prev_line["text"].rstrip() + " " + curr_line["text"].lstrip()
        px0, py0, px1, py1 = prev_line["line_bbox"]
        cx0, cy0, cx1, cy1 = curr_line["line_bbox"]
        prev_line["line_bbox"] = (min(px0, cx0), min(py0, cy0), max(px1, cx1), max(py1, cy1))
        prev_line["font_names"] = list(set(prev_line["font_names"] + curr_line["font_names"]))
        prev_line["total_bold_chars"] += curr_line["total_bold_chars"]
        prev_line["total_nonbold_chars"] += curr_line["total_nonbold_chars"]
        return prev_line

    new_lines = []
    for curr_line in lines:
        while new_lines:
            can_merge_flag, merge_type = can_merge(new_lines[-1], curr_line)
            if can_merge_flag:
                merged = do_merge(new_lines.pop(), curr_line, merge_type)
                curr_line = merged
            else: break
        new_lines.append(curr_line)
    return new_lines

def get_new_blocks(page=None, pdf_path=None, page_num=None):
    """
    Trích xuất và gộp các khối văn bản từ một trang PDF cụ thể.
    """
    try:
        if pdf_path and page_num:
            pdf_document = fitz.open(pdf_path)
            
            if page_num < 1 or page_num > pdf_document.page_count:
                print(f"Lỗi: Số trang {page_num} nằm ngoài giới hạn (1 - {pdf_document.page_count})")
                return []
            page = pdf_document[page_num - 1]

        if not page:
            return []

        blocks = page.get_text("dict")["blocks"]
        lines_data = []

        # ============= Bước 1: Trích xuất thông tin từng dòng =============
        for i, block in enumerate(blocks, start=1):
            if 'lines' not in block: continue
            for line in block["lines"]:
                spans = line.get("spans", [])
                if not spans: continue

                filtered_spans = [span for span in spans if span.get("text", "").strip() != ""]
                if not filtered_spans: continue

                x0_list, y0_list, x1_list, y1_list = [], [], [], []
                for span in filtered_spans:
                    if "bbox" in span:
                        sbbox = span["bbox"]
                        x0_list.append(sbbox[0])
                        y0_list.append(sbbox[1])
                        x1_list.append(sbbox[2])
                        y1_list.append(sbbox[3])

                if x0_list and y0_list and x1_list and y1_list:
                    new_line_bbox = (min(x0_list), min(y0_list), max(x1_list), max(y1_list))
                else:
                    new_line_bbox = line["bbox"]

                full_text = ""
                font_sizes, colors, font_names_set = set(), set(), set()
                bold_flags = []
                longest_span_length = 0
                longest_span_font = None

                for span in filtered_spans:
                    span_text = span["text"]
                    full_text += span_text
                    font_sizes.add(span["size"])
                    colors.add(span["color"])

                    this_font_name = span.get("font", "")
                    font_names_set.add(this_font_name)

                    is_bold = span.get("face", {}).get("bold", False)
                    if not is_bold:
                        bold_keywords = ["bold", "cmbx", "heavy", "demi"]
                        lower_font_name = this_font_name.lower()
                        for kw in bold_keywords:
                            if kw in lower_font_name:
                                is_bold = True
                                break
                    bold_flags.append(is_bold)

                    stripped_span_text = span_text.strip()
                    span_len = len(stripped_span_text)
                    if span_len > longest_span_length:
                        longest_span_length = span_len
                        longest_span_font = this_font_name

                line_is_bold = any(bold_flags)
                stripped_text = full_text.strip()
                if not stripped_text: continue

                # Xóa Bullet point đầu dòng
                if stripped_text.startswith("•"):
                    stripped_text = stripped_text[1:].lstrip()
                    new_line_bbox = (new_line_bbox[0] + 10, new_line_bbox[1], new_line_bbox[2], new_line_bbox[3])
                    full_text = stripped_text

                raw_angle = math.degrees(math.atan2(line.get("dir", [1.0, 0.0])[1], line.get("dir", [1.0, 0.0])[0]))
                angle = snap_angle_func(raw_angle)

                chosen_font_name = longest_span_font if longest_span_font else None
                line_len = len(full_text)

                tb = line_len if line_is_bold else 0
                tnb = 0 if line_is_bold else line_len

                line_data = {
                    "block_index": i,
                    "line_bbox": new_line_bbox,
                    "text": full_text,
                    "font_size": (list(font_sizes)[0] if font_sizes else None),
                    "font_color": (list(colors)[0] if colors else None),
                    "font_name": chosen_font_name,
                    "font_names": list(font_names_set),
                    "rotation_angle": angle,
                    "type": "plain_text",
                    "font_bold": line_is_bold,
                    "indent": 0,
                    "end_indent": 0,
                    "total_bold_chars": tb,
                    "total_nonbold_chars": tnb
                }
                lines_data.append(line_data)

        if not lines_data:
            return []

        # ============= Bước 2: Gộp mảng ngang dọc =============
        merged_horizontally = horizontal_merge(lines_data, max_horizontal_gap=20, max_y_diff=5)
        merged_final = merge_lines(merged_horizontally, check_same_block=False)

        # ============= Bước 3: Phân loại Toán học =============
        temp_block_dict = defaultdict(lambda: {'lines': [], 'total_chars': 0})

        for idx, line_info in enumerate(merged_final):
            text_len = line_info['total_bold_chars'] + line_info['total_nonbold_chars']
            final_text = line_info['text'] or ''

            if final_text:
                result = is_math(line_info['font_names'], text_len, final_text, line_info['font_size'])
                if result == True: line_info['type'] = 'math'
                elif result == "abandon": line_info['type'] = 'abandon'
            else:
                line_info['type'] = 'abandon'

            block_idx = line_info['block_index']
            temp_block_dict[block_idx]['lines'].append((idx, line_info['type'], text_len))
            temp_block_dict[block_idx]['total_chars'] += text_len

        # Gán toàn bộ block ngắn thành Math nếu có chứa Math
        for b_idx, block_data in temp_block_dict.items():
            total_chars = block_data['total_chars']
            lines_in_block = block_data['lines']
            has_math_in_block = any(ln_type == 'math' for (_, ln_type, _) in lines_in_block)
            if (total_chars < 30) and has_math_in_block:
                for (merged_idx, _, _) in lines_in_block:
                    merged_final[merged_idx]['type'] = 'math'

        merged_final = merge_adjacent_math_lines(merged_final)

        # ============= Bước 4: Đóng gói kết quả =============
        new_blocks = []
        for idx, line_info in enumerate(merged_final, start=1):
            if line_info['type'] != 'abandon':
                new_blocks.append([
                    line_info['text'],
                    tuple(line_info['line_bbox']),
                    line_info['type'],
                    line_info['rotation_angle'],
                    line_info['font_color'],
                    line_info['indent'],
                    line_info['font_bold'],
                    line_info['font_size'],
                    line_info['end_indent']
                ])
        return new_blocks

    except Exception as e:
        print(f"Lỗi trích xuất block: {e}")
        return []