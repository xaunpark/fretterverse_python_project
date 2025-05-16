# utils/google_sheets_handler.py
import gspread
from oauth2client.service_account import ServiceAccountCredentials # Hoặc google.oauth2.service_account nếu dùng google-auth
import logging
import os # Để lấy đường dẫn tới file credentials

# Giả sử APP_CONFIG được load từ một module config_loader
# from utils.config_loader import APP_CONFIG

# Khởi tạo logger
logger = logging.getLogger(__name__)

class GoogleSheetsHandler:
    def __init__(self, credentials_json_path=None, config=None):
        """
        Initializes the Google Sheets client.
        'credentials_json_path': Path to the service account JSON file.
        'config': APP_CONFIG object for additional settings like spreadsheet ID.
        """
        self.client = None
        self.config = config if config else {} # Lưu trữ config nếu được truyền vào

        # Xác định đường dẫn file credentials
        # Ưu tiên đường dẫn truyền vào, sau đó là từ config, cuối cùng là một giá trị mặc định (nếu có)
        cred_path = credentials_json_path
        if not cred_path and self.config:
            cred_path = self.config.get('GOOGLE_APPLICATION_CREDENTIALS') # Giả sử key này có trong .env
        
        # Nếu vẫn không có, có thể thử một đường dẫn mặc định hoặc raise lỗi
        if not cred_path:
            # Ví dụ: thử tìm service_account.json trong thư mục config của dự án
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            default_cred_path = os.path.join(project_root, 'config', 'service_account.json')
            if os.path.exists(default_cred_path):
                cred_path = default_cred_path
            else:
                logger.error("Google Sheets credentials JSON path not provided or default path not found.")
                # raise ValueError("Google Sheets credentials JSON path is required.")
                return # Không kết nối nếu không có credentials

        # Phạm vi (scopes) cần thiết
        self.scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.file' # Cần cho gspread để mở sheet bằng ID
        ]
        
        try:
            if os.path.exists(cred_path):
                creds = ServiceAccountCredentials.from_json_keyfile_name(cred_path, self.scopes)
                self.client = gspread.authorize(creds)
                logger.info("Successfully authorized Google Sheets client using service account.")
            else:
                logger.error(f"Credentials file not found at {cred_path}")
                # Có thể thử các phương thức xác thực khác ở đây nếu muốn (ví dụ OAuth2 cho user)
        except Exception as e:
            logger.error(f"Failed to authorize Google Sheets client: {e}")
            self.client = None

    def is_connected(self):
        return self.client is not None

    def get_worksheet(self, spreadsheet_id_or_url, sheet_name_or_gid):
        """
        Helper function to get a specific worksheet object.
        spreadsheet_id_or_url: ID của spreadsheet hoặc URL đầy đủ.
        sheet_name_or_gid: Tên của sheet hoặc GID (số) của sheet.
        """
        if not self.is_connected():
            logger.error("Google Sheets client not connected.")
            return None
        try:
            # Mở spreadsheet bằng ID hoặc URL
            if spreadsheet_id_or_url.startswith("https://"):
                spreadsheet = self.client.open_by_url(spreadsheet_id_or_url)
            else:
                spreadsheet = self.client.open_by_key(spreadsheet_id_or_url) # open_by_key là alias cho open_by_id

            # Mở worksheet bằng tên hoặc GID
            if isinstance(sheet_name_or_gid, int): # Nếu là GID
                worksheet = spreadsheet.get_worksheet_by_id(sheet_name_or_gid)
            else: # Nếu là tên
                worksheet = spreadsheet.worksheet(sheet_name_or_gid)
            
            logger.debug(f"Successfully opened worksheet '{sheet_name_or_gid}' in spreadsheet '{spreadsheet.title}'.")
            return worksheet
        except gspread.exceptions.SpreadsheetNotFound:
            logger.error(f"Spreadsheet not found: {spreadsheet_id_or_url}")
        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"Worksheet not found: {sheet_name_or_gid} in spreadsheet {spreadsheet_id_or_url}")
        except Exception as e:
            logger.error(f"Error opening worksheet: {e}")
        return None

    def get_sheet_data(self, spreadsheet_id_or_url, sheet_name_or_gid, range_name=None, return_as_dicts=True):
        """
        Lấy dữ liệu từ một sheet.
        range_name: Ví dụ "A1:C10" hoặc None để lấy toàn bộ sheet.
        return_as_dicts: Nếu True, trả về list các dicts (hàng đầu tiên là header).
                         Nếu False, trả về list các lists.
        """
        worksheet = self.get_worksheet(spreadsheet_id_or_url, sheet_name_or_gid)
        if not worksheet:
            return None
        try:
            if range_name:
                data = worksheet.get_values(range_name) # Trả về list of lists
            else:
                data = worksheet.get_all_values() # Trả về list of lists

            if return_as_dicts and data:
                headers = data[0]
                dict_list = [dict(zip(headers, row)) for row in data[1:]]
                logger.info(f"Fetched {len(dict_list)} rows as dictionaries from '{sheet_name_or_gid}'.")
                return dict_list
            elif data:
                logger.info(f"Fetched {len(data)} rows as lists from '{sheet_name_or_gid}'.")
                return data
            else:
                logger.info(f"No data found in '{sheet_name_or_gid}' for range '{range_name}'.")
                return []
        except Exception as e:
            logger.error(f"Error getting data from sheet '{sheet_name_or_gid}': {e}")
            return None

    def update_sheet_cell(self, spreadsheet_id_or_url, sheet_name_or_gid, row_num, col_num, value):
        """Cập nhật một ô cụ thể trong sheet (row_num, col_num bắt đầu từ 1)."""
        worksheet = self.get_worksheet(spreadsheet_id_or_url, sheet_name_or_gid)
        if not worksheet:
            return False
        try:
            worksheet.update_cell(row_num, col_num, value)
            logger.info(f"Updated cell ({row_num}, {col_num}) in sheet '{sheet_name_or_gid}' with value: '{str(value)[:50]}...'")
            return True
        except Exception as e:
            logger.error(f"Error updating cell ({row_num}, {col_num}) in sheet '{sheet_name_or_gid}': {e}")
            return False

    def find_row_by_matching_column(self, worksheet, match_column_header, match_value):
        """Helper: Tìm số hàng (index 1) của hàng đầu tiên khớp giá trị trong cột."""
        try:
            # Lấy tất cả dữ liệu để tìm header và cột
            # get_all_records() trả về list of dicts, tiện hơn
            records = worksheet.get_all_records() # Giả sử hàng đầu là header
            if not records:
                logger.warning(f"Sheet '{worksheet.title}' is empty or has no data rows after header.")
                return None

            if match_column_header not in records[0]: # Kiểm tra header có tồn tại không
                logger.error(f"Header '{match_column_header}' not found in sheet '{worksheet.title}'. Available headers: {list(records[0].keys())}")
                return None

            for index, row_dict in enumerate(records):
                if str(row_dict.get(match_column_header, '')).strip() == str(match_value).strip():
                    return index + 2 # +1 vì index của list bắt đầu từ 0, +1 nữa vì hàng header là hàng 1
            logger.debug(f"No row found in sheet '{worksheet.title}' where '{match_column_header}' is '{match_value}'.")
            return None
        except Exception as e:
            logger.error(f"Error finding row in sheet '{worksheet.title}': {e}")
            return None


    def update_sheet_row_by_matching_column(self, spreadsheet_id_or_url, sheet_name_or_gid, 
                                            match_column_header, match_value, data_to_update_dict):
        """
        Cập nhật các ô trong một hàng dựa vào giá trị khớp ở một cột.
        match_column_header: Tên cột để tìm giá trị khớp.
        match_value: Giá trị cần khớp trong cột `match_column_header`.
        data_to_update_dict: Dict với key là header cột và value là giá trị mới.
                             Ví dụ: {'Used': '1', 'Post Title': 'New Title'}
        """
        worksheet = self.get_worksheet(spreadsheet_id_or_url, sheet_name_or_gid)
        if not worksheet:
            return False

        row_num_to_update = self.find_row_by_matching_column(worksheet, match_column_header, match_value)
        
        if not row_num_to_update:
            logger.warning(f"Could not find row to update in '{sheet_name_or_gid}' for {match_column_header}='{match_value}'.")
            return False

        try:
            headers = worksheet.row_values(1) # Lấy header (hàng 1)
            if not headers:
                logger.error(f"Could not retrieve headers from sheet '{sheet_name_or_gid}'.")
                return False

            cells_to_update = []
            for header_to_update, new_value in data_to_update_dict.items():
                try:
                    col_index = headers.index(header_to_update) + 1 # +1 vì col index bắt đầu từ 1
                    cells_to_update.append(gspread.Cell(row_num_to_update, col_index, new_value))
                except ValueError:
                    logger.warning(f"Header '{header_to_update}' not found in sheet '{sheet_name_or_gid}'. Skipping update for this column.")
            
            if cells_to_update:
                worksheet.update_cells(cells_to_update, value_input_option='USER_ENTERED')
                logger.info(f"Successfully updated row {row_num_to_update} in sheet '{sheet_name_or_gid}' for {match_column_header}='{match_value}'. Data: {data_to_update_dict}")
                return True
            else:
                logger.info(f"No valid columns to update for row {row_num_to_update} in sheet '{sheet_name_or_gid}'.")
                return False
        except Exception as e:
            logger.error(f"Error updating row in sheet '{sheet_name_or_gid}': {e}")
            return False
            
    def append_row(self, spreadsheet_id_or_url, sheet_name_or_gid, row_data_list, value_input_option='USER_ENTERED'):
        """
        Thêm một hàng mới vào cuối sheet.
        row_data_list: List các giá trị cho hàng mới.
        """
        worksheet = self.get_worksheet(spreadsheet_id_or_url, sheet_name_or_gid)
        if not worksheet:
            return False
        try:
            worksheet.append_row(row_data_list, value_input_option=value_input_option)
            logger.info(f"Appended row to sheet '{sheet_name_or_gid}': {row_data_list}")
            return True
        except Exception as e:
            logger.error(f"Error appending row to sheet '{sheet_name_or_gid}': {e}")
            return False


# --- Example Usage (cần được gọi từ nơi có APP_CONFIG và file service_account.json) ---
# if __name__ == "__main__":
#     # Load APP_CONFIG
#     # from utils.config_loader import load_app_config
#     # from utils.logging_config import setup_logging
#     # APP_CONFIG = load_app_config()
#     # setup_logging()
#
#     # Khởi tạo handler với config (chứa SPREADSHEET_ID và GOOGLE_APPLICATION_CREDENTIALS)
#     # gsheet_handler = GoogleSheetsHandler(config=APP_CONFIG)
#     # Hoặc truyền trực tiếp path:
#     # creds_path = os.path.join(APP_CONFIG.get('PROJECT_ROOT_DIR'), 'config', 'service_account.json') # Ví dụ
#     # gsheet_handler = GoogleSheetsHandler(credentials_json_path=creds_path)
#
#     # if gsheet_handler.is_connected():
#     #     spreadsheet_id = APP_CONFIG.get('GSHEET_SPREADSHEET_ID')
#     #     keyword_sheet = APP_CONFIG.get('GSHEET_KEYWORD_SHEET_NAME_USED_0') # Sheet đã filter Used=0
#     #     main_keyword_sheet = APP_CONFIG.get('GSHEET_KEYWORD_SHEET_NAME') # Sheet gốc
#
#     #     # Lấy dữ liệu (ví dụ: lấy keyword từ sheet "Keyword Used = 0")
#     #     # Giả sử sheet này chỉ có các keyword chưa được sử dụng
#     #     keywords_to_process = gsheet_handler.get_sheet_data(spreadsheet_id, keyword_sheet, return_as_dicts=True)
#     #     if keywords_to_process:
#     #         first_keyword_data = keywords_to_process[0]
#     #         keyword_value = first_keyword_data.get(APP_CONFIG.get('GSHEET_KEYWORD_COLUMN'))
#     #         logger.info(f"First keyword to process: {keyword_value}")
#
#     #         # Cập nhật hàng trong sheet gốc "Keyword"
#     #         if keyword_value:
#     #             update_data = {
#     #                 APP_CONFIG.get('GSHEET_USED_COLUMN'): "1",
#     #                 APP_CONFIG.get('GSHEET_POST_TITLE_COLUMN'): f"Processed: {keyword_value}",
#     #                 APP_CONFIG.get('GSHEET_POST_ID_COLUMN'): "12345",
#     #                 APP_CONFIG.get('GSHEET_POST_URL_COLUMN'): f"https://example.com/{keyword_value.replace(' ', '-')}"
#     #             }
#     #             success = gsheet_handler.update_sheet_row_by_matching_column(
#     #                 spreadsheet_id,
#     #                 main_keyword_sheet, # Cập nhật trên sheet gốc
#     #                 APP_CONFIG.get('GSHEET_KEYWORD_COLUMN'), # Cột để khớp
#     #                 keyword_value, # Giá trị để khớp
#     #                 update_data # Dữ liệu để cập nhật
#     #             )
#     #             if success:
#     #                 logger.info(f"Successfully updated sheet for keyword: {keyword_value}")
#     #             else:
#     #                 logger.error(f"Failed to update sheet for keyword: {keyword_value}")
#         # else:
#         #     logger.info("No keywords to process or error fetching data.")
#
#         # # Test update cell
#         # gsheet_handler.update_sheet_cell(spreadsheet_id, main_keyword_sheet, 2, 2, "TEST_UPDATE_CELL")
#
#         # # Test append row
#         # gsheet_handler.append_row(spreadsheet_id, main_keyword_sheet, ["New Keyword Test", "0", "no", "no", "", "", ""])