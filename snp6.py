import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os
import time
from datetime import datetime
import re
import io
import zipfile
from typing import Dict, List, Any
import hashlib

# Try Word document processing
try:
    from docx import Document
    from docx.shared import RGBColor, Pt
    from docx.enum.text import WD_COLOR_INDEX
    PYTHON_DOCX_AVAILABLE = True
except ImportError:
    PYTHON_DOCX_AVAILABLE = False
    st.error("python-docx not available. Please add it to requirements.txt")

# Try reportlab for PDF generation
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import Color, red, orange, yellow, lightgrey
    from reportlab.lib.units import inch
    from reportlab.platypus.flowables import KeepTogether
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    st.warning("reportlab not available - PDF generation will be disabled")

# Excel import
try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False
    st.error("openpyxl not available. Please add it to requirements.txt")

# Try OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    st.error("openai not available. Please add it to requirements.txt")

# ============ CONFIGURATION ============
# Configuration optimized for large files
MAX_CHARS_PER_CHUNK = 4000
OVERLAP_CHARS = 200
MAX_TOKENS_OUTPUT = 1000
CHUNK_DELAY = 1
MAX_RETRIES = 3

# ============ S&P VIOLATION RULES ============
VIOLATION_RULES = {
    "National_Symbols_Anthem": {
        "description": "Improper use of national symbols, anthem, flag, or government emblems",
        "keywords": ["national anthem", "flag", "tricolor", "ashoka chakra", "government logo"],
        "severity": "critical"
    },
    "PI_Data_Brand_References": {
        "description": "Personal information exposure, unauthorized brand references, trademark violations",
        "keywords": ["personal data", "phone number", "address", "brand name", "trademark"],
        "severity": "high"
    },
    "Credits_Endorsements": {
        "description": "Missing credits, unauthorized endorsements, celebrity impersonation",
        "keywords": ["credit", "endorsement", "celebrity", "sponsor", "testimonial"],
        "severity": "medium"
    },
    "Religious_Cultural_Sensitivity": {
        "description": "Religious insensitivity, cultural stereotypes, communal bias, offensive content",
        "keywords": ["religion", "god", "hindu", "muslim", "christian", "sikh", "culture", "caste"],
        "severity": "critical"
    },
    "Animal_Welfare": {
        "description": "Animal cruelty, unsafe animal handling, wildlife protection violations",
        "keywords": ["animal", "cruelty", "pet", "wildlife", "zoo", "circus"],
        "severity": "high"
    },
    "Disclaimers_Warnings": {
        "description": "Missing disclaimers, inadequate warnings, safety information gaps",
        "keywords": ["disclaimer", "warning", "caution", "safety", "risk"],
        "severity": "medium"
    },
    "Smoking_Alcohol_Social_Evils": {
        "description": "Glorification of smoking, alcohol abuse, gambling, or other social evils",
        "keywords": ["smoke", "cigarette", "alcohol", "drink", "gambling", "bet", "drugs"],
        "severity": "high"
    },
    "Child_Safety": {
        "description": "Content harmful to minors, inappropriate child representation, safety risks",
        "keywords": ["child", "minor", "kid", "school", "unsafe", "inappropriate"],
        "severity": "critical"
    },
    "Violence_Self_Harm": {
        "description": "Graphic violence, self-harm content, suicide references, dangerous activities",
        "keywords": ["violence", "fight", "blood", "suicide", "self-harm", "dangerous", "weapon"],
        "severity": "critical"
    },
    "Substances_Addiction": {
        "description": "Drug use promotion, addiction glorification, substance abuse normalization",
        "keywords": ["drugs", "addiction", "substance", "abuse", "dealer", "high", "overdose"],
        "severity": "critical"
    }
}

def main():
    st.set_page_config(
        page_title="S&P Compliance Analyzer",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🔍 S&P Compliance Analyzer")
    st.markdown("**Standards & Practices Compliance Checker for Indian Digital Media**")
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # API Key input
        api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            help="Enter your OpenAI API key for content analysis"
        )
        
        if not api_key:
            st.warning("Please enter your OpenAI API key to proceed")
        
        st.header("📊 Processing Settings")
        chunk_size = st.slider("Chunk Size (chars)", 2000, 8000, MAX_CHARS_PER_CHUNK)
        delay = st.slider("API Delay (seconds)", 0, 5, CHUNK_DELAY)
        
        # System status
        st.header("📚 System Status")
        if PYTHON_DOCX_AVAILABLE:
            st.success("✅ DOCX Processing")
        else:
            st.error("❌ DOCX Processing")
        
        if REPORTLAB_AVAILABLE:
            st.success("✅ PDF Generation")
        else:
            st.warning("⚠️ PDF Generation")
        
        if EXCEL_AVAILABLE:
            st.success("✅ Excel Reports")
        else:
            st.error("❌ Excel Reports")
        
        if OPENAI_AVAILABLE:
            st.success("✅ OpenAI Integration")
        else:
            st.error("❌ OpenAI Integration")
    
    # Main content area
    tab1, tab2, tab3 = st.tabs(["📤 Upload & Analyze", "📊 Results", "📋 Violation Rules"])
    
    with tab1:
        st.header("📤 Document Upload")
        
        uploaded_file = st.file_uploader(
            "Choose a DOCX file",
            type=['docx'],
            help="Upload a Microsoft Word document for S&P compliance analysis"
        )
        
        if uploaded_file is not None:
            if not api_key:
                st.error("Please enter your OpenAI API key in the sidebar")
                return
            
            # Save uploaded file temporarily
            with st.spinner("Processing document..."):
                # Here you would implement the analysis logic
                # This is a simplified version - you'd need to adapt your existing functions
                
                st.success("✅ Document uploaded successfully!")
                st.info(f"**File:** {uploaded_file.name}")
                st.info(f"**Size:** {len(uploaded_file.read())/1024:.1f} KB")
                
                # Reset file pointer
                uploaded_file.seek(0)
                
                if st.button("🔍 Start Analysis", type="primary"):
                    # This is where you'd call your analysis functions
                    st.success("Analysis would start here!")
                    st.balloons()
    
    with tab2:
        st.header("📊 Analysis Results")
        
        # Placeholder for results
        if st.session_state.get('analysis_complete', False):
            # Display results here
            st.success("Analysis completed!")
        else:
            st.info("Upload and analyze a document to see results here.")
            
            # Show demo chart
            st.subheader("📈 Sample Violation Distribution")
            demo_data = pd.DataFrame({
                'Severity': ['Critical', 'High', 'Medium', 'Low'],
                'Count': [5, 12, 8, 3],
                'Color': ['#FF4444', '#FF8800', '#FFCC00', '#CCCCCC']
            })
            
            fig = px.bar(
                demo_data, 
                x='Severity', 
                y='Count',
                color='Severity',
                color_discrete_map={
                    'Critical': '#FF4444',
                    'High': '#FF8800', 
                    'Medium': '#FFCC00',
                    'Low': '#CCCCCC'
                },
                title="Violations by Severity (Demo Data)"
            )
            st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        st.header("📋 S&P Violation Categories")
        
        for rule_name, rule_data in VIOLATION_RULES.items():
            severity = rule_data['severity']
            
            # Color code by severity
            if severity == 'critical':
                st.error(f"🔴 **{rule_name.replace('_', ' ')}** (Critical)")
            elif severity == 'high':
                st.warning(f"🟠 **{rule_name.replace('_', ' ')}** (High)")
            else:
                st.info(f"🟡 **{rule_name.replace('_', ' ')}** (Medium)")
            
            st.write(rule_data['description'])
            st.write(f"**Keywords:** {', '.join(rule_data['keywords'])}")
            st.divider()
    
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center'>
            <p>🔍 S&P Compliance Analyzer - Built for Indian Digital Media Standards</p>
            <p><small>Ensure your content meets broadcasting and digital media compliance requirements</small></p>
        </div>
        """, 
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
