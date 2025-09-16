# --- Login form (buat generik & tahan perubahan minor UI) ---
SEL_USER = 'input[placeholder="Username"], input[name="username"], input[autocomplete="username"]'
SEL_PASS = 'input[placeholder="Password"], input[name="password"], input[type="password"]'
SEL_BTN_LOGIN = 'button:has-text("Login"), .el-button:has-text("Login"), button[type="submit"]'

# --- Penanda dashboard siap ---
DASHBOARD_PROBES = [
    ".layout-setting-box .el-select",
    ".layout-grid-content",
    ".preview-box",
]

# --- Layout dropdown & dialog konfirmasi ---
LAYOUT_DROPDOWN_INPUT = ".layout-setting-box .el-select .el-input__inner"
LAYOUT_OPTION_ROW = ".layout-tool-select .layout-select-option"
LAYOUT_DIALOG = ".el-message-box"
LAYOUT_CONFIRM_OK = '.el-message-box__btns .el-button--primary'
LAYOUT_CONFIRM_CANCEL = '.el-message-box__btns .el-button:not(.el-button--primary)'

# --- Source list (panel kanan) ---
SOURCE_LIST_CONTAINER = ".discovery-list-box"
SOURCE_ITEM = ".discovery-list-item"
SOURCE_ITEM_NAME = f'{SOURCE_ITEM} span[title]'

# --- Grid (area utama) ---
GRID_CONTAINER = ".layout-grid-content"
GRID_CELL = f"{GRID_CONTAINER} .grid-list-item"

LIST_SOURCE_ITEM = '[data-source-id^="source_"]'
