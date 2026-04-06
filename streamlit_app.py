import streamlit as st
import pandas as pd
from datetime import datetime
import re
from io import BytesIO

st.set_page_config(page_title="KYC Validator", layout="wide")

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
            'Name of the Borrower': 'count'
        }).rename(columns={'Name of the Borrower': 'occurrence_count'})
        
        duplicates = pan_counts[pan_counts['occurrence_count'] > 1]
        return duplicates
    
    @staticmethod
    def check_missing(df):
        """Find missing PAN values"""
        return df[df['PAN'].isna() | (df['PAN'] == '')][['UCIC', 'Name of the Borrower', 'PAN']]


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
        mobile_df = df[df['Mobile'].notna()].copy()
        mobile_counts = mobile_df.groupby('Mobile').agg({
            'UCIC': lambda x: list(set(x)),
            'PAN': lambda x: list(set(x)),
            'Name of the Borrower': 'count'
        }).rename(columns={'Name of the Borrower': 'occurrence_count'})
        
        duplicates = mobile_counts[mobile_counts['occurrence_count'] > 1]
        return duplicates
    
    @staticmethod
    def check_invalid_format(df):
        """Find mobile numbers with invalid format"""
        invalid = df[
            (df['Mobile'].notna()) & 
            (~df['Mobile'].astype(str).str.match(r'^\d{10}$'))
        ][['UCIC', 'Name of the Borrower', 'Mobile']]
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
            borrower_names = df[df['UCIC'] == ucic]['Name of the Borrower'].unique()
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
            borrower_names = df[df['PAN'] == pan]['Name of the Borrower'].unique()
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
st.markdown("Upload your KYC Excel/CSV file to check for data quality issues.")

# File upload
uploaded_file = st.file_uploader("Upload KYC file (CSV or Excel)", type=['csv', 'xlsx', 'xls'])

if uploaded_file is not None:
    # Read file
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        st.success(f"✅ File loaded successfully! Total records: {len(df)}")
        
        # Check for required columns
        required_columns = ['UCIC', 'PAN', 'Name of the Borrower', 'Mobile']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            st.error(f"❌ Missing required columns: {', '.join(missing_columns)}")
            st.info(f"📋 Available columns in your file:\n{', '.join(df.columns.tolist())}")
            st.info("✅ Required columns: UCIC, PAN, Name of the Borrower, Mobile")
            st.stop()
        
        # Create tabs for different validations
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Summary", "🆔 PAN Validation", "📱 Mobile Validation", "🔗 UCIC-PAN Mapping"])
        
        # ============ TAB 1: SUMMARY ============
        with tab1:
            st.subheader("📋 Data Summary")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Records", len(df))
            col2.metric("Unique UCICs", df['UCIC'].nunique())
            col3.metric("Missing PANs", df['PAN'].isna().sum())
            col4.metric("Missing Mobile", df['Mobile'].isna().sum())
            
            st.subheader("🔴 Overall Issues Found")
            issues_summary = []
            
            # PAN issues
            invalid_pan = df[~df['PAN'].apply(lambda x: PANValidator.is_valid_format(x) if pd.notna(x) else False)].shape[0]
            dup_pan = len(PANValidator.check_duplicates(df))
            issues_summary.append(f"🆔 PAN Issues: {invalid_pan} invalid format + {dup_pan} duplicates")
            
            # Mobile issues
            invalid_mobile = len(MobileValidator.check_invalid_format(df))
            dup_mobile = len(MobileValidator.check_duplicates(df))
            issues_summary.append(f"📱 Mobile Issues: {invalid_mobile} invalid format + {dup_mobile} duplicates")
            
            # UCIC issues
            multiple_pan_ucic = len(UCICValidator.check_multiple_pan_per_ucic(df))
            multiple_ucic_pan = len(UCICValidator.check_multiple_ucic_per_pan(df))
            issues_summary.append(f"🔗 UCIC-PAN Issues: {multiple_pan_ucic} UCIC with multiple PANs + {multiple_ucic_pan} PAN with multiple UCICs")
            
            for issue in issues_summary:
                st.info(issue)
        
        # ============ TAB 2: PAN VALIDATION ============
        with tab2:
            st.subheader("🆔 PAN Number Validation")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Invalid PAN Format")
                invalid_pans = df[~df['PAN'].apply(lambda x: PANValidator.is_valid_format(x) if pd.notna(x) else False)][
                    ['UCIC', 'Name of the Borrower', 'PAN']
                ]
                st.dataframe(invalid_pans, use_container_width=True)
                st.caption(f"Total: {len(invalid_pans)} records")
            
            with col2:
                st.subheader("Duplicate PANs")
                dup_pans = PANValidator.check_duplicates(df)
                if len(dup_pans) > 0:
                    dup_pans_display = dup_pans.reset_index()
                    dup_pans_display['UCICs'] = dup_pans_display['UCIC'].apply(lambda x: ', '.join(map(str, x)))
                    dup_pans_display = dup_pans_display[['PAN', 'occurrence_count', 'UCICs']]
                    st.dataframe(dup_pans_display, use_container_width=True)
                else:
                    st.success("✅ No duplicate PANs found!")
            
            st.subheader("Missing PAN Numbers")
            missing_pans = PANValidator.check_missing(df)
            st.dataframe(missing_pans, use_container_width=True)
            st.caption(f"Total: {len(missing_pans)} records")
        
        # ============ TAB 3: MOBILE VALIDATION ============
        with tab3:
            st.subheader("📱 Mobile Number Validation")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Invalid Mobile Format")
                invalid_mobiles = MobileValidator.check_invalid_format(df)
                st.dataframe(invalid_mobiles, use_container_width=True)
                st.caption(f"Total: {len(invalid_mobiles)} records")
            
            with col2:
                st.subheader("Duplicate Mobile Numbers")
                dup_mobiles = MobileValidator.check_duplicates(df)
                if len(dup_mobiles) > 0:
                    dup_mobiles_display = dup_mobiles.reset_index()
                    dup_mobiles_display['UCICs'] = dup_mobiles_display['UCIC'].apply(lambda x: ', '.join(map(str, x)))
                    dup_mobiles_display['PANs'] = dup_mobiles_display['PAN'].apply(lambda x: ', '.join(map(str, x)))
                    dup_mobiles_display = dup_mobiles_display[['Mobile', 'occurrence_count', 'UCICs', 'PANs']]
                    st.dataframe(dup_mobiles_display, use_container_width=True)
                else:
                    st.success("✅ No duplicate mobile numbers found!")
        
        # ============ TAB 4: UCIC-PAN MAPPING ============
        with tab4:
            st.subheader("🔗 UCIC to PAN Mapping")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("UCIC with Multiple PANs")
                multiple_pan_ucic = UCICValidator.check_multiple_pan_per_ucic(df)
                if len(multiple_pan_ucic) > 0:
                    st.dataframe(multiple_pan_ucic, use_container_width=True)
                    st.caption(f"Total: {len(multiple_pan_ucic)} UCICs")
                else:
                    st.success("✅ No UCIC mapped to multiple PANs!")
            
            with col2:
                st.subheader("PAN with Multiple UCICs")
                multiple_ucic_pan = UCICValidator.check_multiple_ucic_per_pan(df)
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
            invalid_pans = df[~df['PAN'].apply(lambda x: PANValidator.is_valid_format(x) if pd.notna(x) else False)][
                ['UCIC', 'Name of the Borrower', 'PAN']
            ]
            if len(invalid_pans) > 0:
                sheets_data['Invalid PAN Format'] = invalid_pans
            
            # 2. Missing PANs
            missing_pans = PANValidator.check_missing(df)
            if len(missing_pans) > 0:
                sheets_data['Missing PANs'] = missing_pans
            
            # 3. Invalid Mobile Format
            invalid_mobiles = MobileValidator.check_invalid_format(df)
            if len(invalid_mobiles) > 0:
                sheets_data['Invalid Mobile Format'] = invalid_mobiles
            
            # 4. UCIC with Multiple PANs
            multiple_pan_ucic = UCICValidator.check_multiple_pan_per_ucic(df)
            if len(multiple_pan_ucic) > 0:
                sheets_data['UCIC Multiple PANs'] = multiple_pan_ucic
            
            # 5. PAN with Multiple UCICs
            multiple_ucic_pan = UCICValidator.check_multiple_ucic_per_pan(df)
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

# Initialize git
git init

# Add all files
git add .

# Create first commit
git commit -m "Initial commit: KYC Validator app"

# Add remote repository (replace USERNAME with your GitHub username)
git remote add origin https://github.com/USERNAME/kyc-validator.git

# Push to GitHub
git branch -M main
git push -u origin main

