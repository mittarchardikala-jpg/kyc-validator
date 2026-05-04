import streamlit as st
import pandas as pd
from datetime import datetime
import re
from io import BytesIO
import requests

st.set_page_config(page_title="KYC Validator", layout="wide")

# ==================== LOAD CODE FROM CLOUD ====================

@st.cache_resource
def get_app_version():
    """Get app version from GitHub"""
    try:
        response = requests.get(
            "https://api.github.com/repos/mittarchardikala-jpg/kyc-validator/commits",
            params={"per_page": 1}
        )
        if response.status_code == 200:
            return response.json()[0]['sha'][:7]
    except:
        pass
    return "Local"

# ==================== HELPER FUNCTION: NORMALIZE COLUMN NAMES ====================

def normalize_column_name(col_name):
    """Normalize column name: lowercase, remove extra spaces, handle variations"""
    col_lower = str(col_name).lower().strip()
    # Remove extra spaces
    col_lower = ' '.join(col_lower.split())
    return col_lower

def get_column_mapping(df):
    """Create a mapping of normalized column names to actual column names"""
    mapping = {}
    for col in df.columns:
        normalized = normalize_column_name(col)
        mapping[normalized] = col
    return mapping

def find_column(df, column_mapping, target_names):
    """Find a column by various name variations (case and space insensitive)"""
    for target in target_names:
        normalized_target = normalize_column_name(target)
        if normalized_target in column_mapping:
            return column_mapping[normalized_target]
    return None

def prepare_dataframe(df):
    """
    Prepare dataframe by:
    1. Normalizing column names (case and space insensitive)
    2. Converting mobile numbers from text to digits
    """
    column_mapping = get_column_mapping(df)
    
    # Define column variations
    required_columns = {
        'ucic': ['ucic', 'ucic number', 'ucic_number'],
        'pan': ['pan', 'pan number', 'pan_number'],
        'name': ['name of the borrower', 'name of borrower', 'borrower name', 'customer name'],
        'mobile': ['mobile', 'mobile number', 'mobile_number', 'phone', 'phone number']
    }
    
    # Find actual column names
    found_columns = {}
    for key, variations in required_columns.items():
        col = find_column(df, column_mapping, variations)
        if col:
            found_columns[key] = col
    
    # Check if all required columns found
    if len(found_columns) < 4:
        missing = [k for k in required_columns.keys() if k not in found_columns]
        return None, missing, None
    
    # Rename columns to standard names
    df_copy = df.copy()
    rename_dict = {v: k.upper() for k, v in found_columns.items()}
    df_copy.rename(columns=rename_dict, inplace=True)
    
    # Convert mobile numbers: remove non-digits and handle text-to-number conversion
    if 'MOBILE' in df_copy.columns:
        df_copy['MOBILE'] = df_copy['MOBILE'].apply(lambda x: convert_mobile_to_digits(x))
    
    return df_copy, None, found_columns

def convert_mobile_to_digits(mobile):
    """Convert mobile number from text or mixed format to digits only"""
    if pd.isna(mobile):
        return mobile
    
    mobile_str = str(mobile).strip()
    
    # Extract only digits
    digits_only = re.sub(r'\D', '', mobile_str)
    
    # If we got digits, return as string (to preserve leading zeros if any)
    if digits_only:
        return digits_only
    
    return mobile_str  # Return original if no digits found

# ==================== VALIDATORS ====================

class PANValidator:
    """Validates PAN numbers for format and duplicates"""
    
    @staticmethod
    def is_valid_format(pan):
        """Check if PAN follows format: 5 letters, 4 digits, 1 letter"""
        if pd.isna(pan):
            return False
        pan_str = str(pan).strip().upper()
        pan_regex = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]$')
        return bool(pan_regex.match(pan_str))
    
    @staticmethod
    def check_duplicates(df):
        """Find duplicate PANs across different customers"""
        pan_counts = df[df['PAN'].notna()].groupby('PAN').agg({
            'UCIC': lambda x: list(set(x)),
            'NAME': 'count'
        }).rename(columns={'NAME': 'occurrence_count'})
        
        duplicates = pan_counts[pan_counts['occurrence_count'] > 1]
        return duplicates
    
    @staticmethod
    def check_missing(df):
        """Find missing PAN values"""
        return df[df['PAN'].isna() | (df['PAN'] == '')][['UCIC', 'NAME', 'PAN']]


class MobileValidator:
    """Validates mobile numbers for format and duplicates"""
    
    @staticmethod
    def is_valid_format(mobile_number):
        """Check if mobile number is valid (10 digits)"""
        if pd.isna(mobile_number):
            return False
        mobile_str = str(mobile_number).strip()
        return len(mobile_str) == 10 and mobile_str.isdigit()
    
    @staticmethod
    def check_duplicates(df):
        """Find duplicate mobile numbers across different customers"""
        mobile_df = df[df['MOBILE'].notna()].copy()
        mobile_counts = mobile_df.groupby('MOBILE').agg({
            'UCIC': lambda x: list(set(x)),
            'PAN': lambda x: list(set(x)),
            'NAME': 'count'
        }).rename(columns={'NAME': 'occurrence_count'})
        
        duplicates = mobile_counts[mobile_counts['occurrence_count'] > 1]
        return duplicates
    
    @staticmethod
    def check_invalid_format(df):
        """Find mobile numbers with invalid format"""
        invalid = df[
            (df['MOBILE'].notna()) & 
            (~df['MOBILE'].astype(str).str.match(r'^\d{10}$'))
        ][['UCIC', 'NAME', 'MOBILE']]
        return invalid


class UCICValidator:
    """Validates UCIC and PAN mappings"""
    
    @staticmethod
    def check_multiple_pan_per_ucic(df):
        """Find UCIC mapped to multiple PANs"""
        ucic_pan_mapping = df[df['PAN'].notna()].groupby('UCIC')['PAN'].apply(lambda x: list(set(x)))
        multiple_pans = ucic_pan_mapping[ucic_pan_mapping.apply(len) > 1]
        
        result_list = []
        for ucic, pans in multiple_pans.items():
            borrower_names = df[df['UCIC'] == ucic]['NAME'].unique()
            result_list.append({
                'UCIC': ucic,
                'PAN_count': len(pans),
                'PANs': ', '.join(pans),
                'Borrower Names': ', '.join(borrower_names)
            })
        return pd.DataFrame(result_list) if result_list else pd.DataFrame()
    
    @staticmethod
    def check_multiple_ucic_per_pan(df):
        """Find PAN mapped to multiple UCICs"""
        pan_ucic_mapping = df[df['PAN'].notna()].groupby('PAN')['UCIC'].apply(lambda x: list(set(x)))
        multiple_ucics = pan_ucic_mapping[pan_ucic_mapping.apply(len) > 1]
        
        result_list = []
        for pan, ucics in multiple_ucics.items():
            borrower_names = df[df['PAN'] == pan]['NAME'].unique()
            result_list.append({
                'PAN': pan,
                'UCIC_count': len(ucics),
                'UCICs': ', '.join(map(str, ucics)),
                'Borrower Names': ', '.join(borrower_names)
            })
        return pd.DataFrame(result_list) if result_list else pd.DataFrame()


# ==================== HELPER FUNCTION ====================

def create_excel_file(sheets_dict):
    """Create an Excel file with multiple sheets"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in sheets_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output


# ==================== STREAMLIT APP ====================

st.title("🔍 KYC Validator")
st.markdown("---")
st.markdown("Upload your KYC file to check for data quality issues.")

# Upload section with version info
col1, col2 = st.columns([3, 1])
with col1:
    uploaded_file = st.file_uploader("Upload KYC file (CSV, Excel, or XLSB)", type=['csv', 'xlsx', 'xls', 'xlsb'])

with col2:
    app_version = get_app_version()
    st.caption(f"📡 Version: {app_version}")

if uploaded_file is not None:
    # Read file
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        elif uploaded_file.name.endswith('.xlsb'):
            # For XLSB files, use pyxlsb
            try:
                import pyxlsb
                from pyxlsb import open_workbook
                df = pd.read_excel(uploaded_file, engine='pyxlsb')
            except ImportError:
                st.error("❌ XLSB support requires 'pyxlsb' package. Please contact admin.")
                st.stop()
        else:
            df = pd.read_excel(uploaded_file)
        
        st.success(f"✅ File loaded successfully! Total records: {len(df)}")
        
        # Prepare dataframe with column normalization
        df_processed, missing_cols, col_mapping = prepare_dataframe(df)
        
        if df_processed is None:
            st.error(f"❌ Missing or unrecognized required columns: {', '.join(missing_cols)}")
            st.info(f"📋 Available columns in your file:\n{', '.join(df.columns.tolist())}")
            st.info("✅ Required columns (any variation): UCIC, PAN, Name of the Borrower, Mobile")
            st.info("Examples: 'UCIC Number', 'ucic', 'Pan Number', 'Customer Name', 'Phone Number', etc.")
            st.stop()
        
        # Create tabs for different validations
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Summary", "🆔 PAN Validation", "📱 Mobile Validation", "🔗 UCIC-PAN Mapping"])
        
        # ============ TAB 1: SUMMARY ============
        with tab1:
            st.subheader("📋 Data Summary")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Records", len(df_processed))
            col2.metric("Unique UCICs", df_processed['UCIC'].nunique())
            col3.metric("Missing PANs", df_processed['PAN'].isna().sum())
            col4.metric("Missing Mobile", df_processed['MOBILE'].isna().sum())
            
            st.subheader("🔴 Overall Issues Found")
            issues_summary = []
            
            # PAN issues
            invalid_pan = df_processed[~df_processed['PAN'].apply(lambda x: PANValidator.is_valid_format(x) if pd.notna(x) else False)].shape[0]
            dup_pan = len(PANValidator.check_duplicates(df_processed))
            issues_summary.append(f"🆔 PAN Issues: {invalid_pan} invalid format + {dup_pan} duplicates")
            
            # Mobile issues
            invalid_mobile = len(MobileValidator.check_invalid_format(df_processed))
            dup_mobile = len(MobileValidator.check_duplicates(df_processed))
            issues_summary.append(f"📱 Mobile Issues: {invalid_mobile} invalid format + {dup_mobile} duplicates")
            
            # UCIC issues
            multiple_pan_ucic = len(UCICValidator.check_multiple_pan_per_ucic(df_processed))
            multiple_ucic_pan = len(UCICValidator.check_multiple_ucic_per_pan(df_processed))
            issues_summary.append(f"🔗 UCIC-PAN Issues: {multiple_pan_ucic} UCIC with multiple PANs + {multiple_ucic_pan} PAN with multiple UCICs")
            
            for issue in issues_summary:
                st.info(issue)
        
        # ============ TAB 2: PAN VALIDATION ============
        with tab2:
            st.subheader("🆔 PAN Number Validation")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Invalid PAN Format")
                invalid_pans = df_processed[~df_processed['PAN'].apply(lambda x: PANValidator.is_valid_format(x) if pd.notna(x) else False)][
                    ['UCIC', 'NAME', 'PAN']
                ]
                st.dataframe(invalid_pans, use_container_width=True)
                st.caption(f"Total: {len(invalid_pans)} records")
            
            with col2:
                st.subheader("Duplicate PANs")
                dup_pans = PANValidator.check_duplicates(df_processed)
                if len(dup_pans) > 0:
                    dup_pans_display = dup_pans.reset_index()
                    dup_pans_display['UCICs'] = dup_pans_display['UCIC'].apply(lambda x: ', '.join(map(str, x)))
                    dup_pans_display = dup_pans_display[['PAN', 'occurrence_count', 'UCICs']]
                    st.dataframe(dup_pans_display, use_container_width=True)
                else:
                    st.success("✅ No duplicate PANs found!")
            
            st.subheader("Missing PAN Numbers")
            missing_pans = PANValidator.check_missing(df_processed)
            st.dataframe(missing_pans, use_container_width=True)
            st.caption(f"Total: {len(missing_pans)} records")
        
        # ============ TAB 3: MOBILE VALIDATION ============
        with tab3:
            st.subheader("📱 Mobile Number Validation")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Invalid Mobile Format")
                invalid_mobiles = MobileValidator.check_invalid_format(df_processed)
                st.dataframe(invalid_mobiles, use_container_width=True)
                st.caption(f"Total: {len(invalid_mobiles)} records")
            
            with col2:
                st.subheader("Duplicate Mobile Numbers")
                dup_mobiles = MobileValidator.check_duplicates(df_processed)
                if len(dup_mobiles) > 0:
                    dup_mobiles_display = dup_mobiles.reset_index()
                    dup_mobiles_display['UCICs'] = dup_mobiles_display['UCIC'].apply(lambda x: ', '.join(map(str, x)))
                    dup_mobiles_display['PANs'] = dup_mobiles_display['PAN'].apply(lambda x: ', '.join(map(str, x)))
                    dup_mobiles_display = dup_mobiles_display[['MOBILE', 'occurrence_count', 'UCICs', 'PANs']]
                    st.dataframe(dup_mobiles_display, use_container_width=True)
                else:
                    st.success("✅ No duplicate mobile numbers found!")
        
        # ============ TAB 4: UCIC-PAN MAPPING ============
        with tab4:
            st.subheader("🔗 UCIC to PAN Mapping")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("UCIC with Multiple PANs")
                multiple_pan_ucic = UCICValidator.check_multiple_pan_per_ucic(df_processed)
                if len(multiple_pan_ucic) > 0:
                    st.dataframe(multiple_pan_ucic, use_container_width=True)
                    st.caption(f"Total: {len(multiple_pan_ucic)} UCICs")
                else:
                    st.success("✅ No UCIC mapped to multiple PANs!")
            
            with col2:
                st.subheader("PAN with Multiple UCICs")
                multiple_ucic_pan = UCICValidator.check_multiple_ucic_per_pan(df_processed)
                if len(multiple_ucic_pan) > 0:
                    st.dataframe(multiple_ucic_pan, use_container_width=True)
                    st.caption(f"Total: {len(multiple_ucic_pan)} PANs")
                else:
                    st.success("✅ No PAN mapped to multiple UCICs!")
        
        # ============ COMPREHENSIVE EXCEL REPORT ============
        st.markdown("---")
        st.subheader("📊 Generate Excel Report")
        
        if st.button("Generate Complete Error Report (Excel)"):
            sheets_data = {}
            
            # 1. Invalid PAN Format
            invalid_pans = df_processed[~df_processed['PAN'].apply(lambda x: PANValidator.is_valid_format(x) if pd.notna(x) else False)][
                ['UCIC', 'NAME', 'PAN']
            ]
            if len(invalid_pans) > 0:
                sheets_data['Invalid PAN Format'] = invalid_pans
            
            # 2. Missing PANs
            missing_pans = PANValidator.check_missing(df_processed)
            if len(missing_pans) > 0:
                sheets_data['Missing PANs'] = missing_pans
            
            # 3. Invalid Mobile Format
            invalid_mobiles = MobileValidator.check_invalid_format(df_processed)
            if len(invalid_mobiles) > 0:
                sheets_data['Invalid Mobile Format'] = invalid_mobiles
            
            # 4. UCIC with Multiple PANs
            multiple_pan_ucic = UCICValidator.check_multiple_pan_per_ucic(df_processed)
            if len(multiple_pan_ucic) > 0:
                sheets_data['UCIC Multiple PANs'] = multiple_pan_ucic
            
            # 5. PAN with Multiple UCICs
            multiple_ucic_pan = UCICValidator.check_multiple_ucic_per_pan(df_processed)
            if len(multiple_ucic_pan) > 0:
                sheets_data['PAN Multiple UCICs'] = multiple_ucic_pan
            
            # 6. Summary Sheet
            summary_data = {
                'Validation Type': [
                    'Invalid PAN Format',
                    'Missing PANs',
                    'Invalid Mobile Format',
                    'UCIC with Multiple PANs',
                    'PAN with Multiple UCICs'
                ],
                'Count': [
                    len(invalid_pans),
                    len(missing_pans),
                    len(invalid_mobiles),
                    len(multiple_pan_ucic),
                    len(multiple_ucic_pan)
                ]
            }
            sheets_data['Summary'] = pd.DataFrame(summary_data)
            
            if sheets_data:
                # Create Excel file
                excel_file = create_excel_file(sheets_data)
                
                st.success("✅ Report generated successfully!")
                
                # Download button
                st.download_button(
                    label="📥 Download Excel Report",
                    data=excel_file,
                    file_name=f"KYC_Validation_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.success("✅ No errors found in the KYC data!")
    
    except Exception as e:
        st.error(f"❌ Error processing file: {str(e)}")

else:
    st.info("📤 Please upload a KYC file to get started!")
