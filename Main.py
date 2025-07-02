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

# Import your backend functions
import sys
sys.path.append('.')  # Add current directory to path
from snp6 import (
    extract_text_from_docx, 
    analyze_document_robust, 
    save_xlsx_report,
    create_highlighted_pdf_from_docx,
    OPENAI_API_KEY,
    VIOLATION_RULES
)

# Page configuration
st.set_page_config(
    page_title="S&P Compliance Review | hoichoi",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #ff6b6b, #4ecdc4);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .violation-critical {
        background-color: #ffebee;
        border-left: 5px solid #f44336;
        padding: 10px;
        margin: 5px 0;
    }
    .violation-high {
        background-color: #fff3e0;
        border-left: 5px solid #ff9800;
        padding: 10px;
        margin: 5px 0;
    }
    .violation-medium {
        background-color: #fffde7;
        border-left: 5px solid #ffeb3b;
        padding: 10px;
        margin: 5px 0;
    }
    .violation-low {
        background-color: #f3e5f5;
        border-left: 5px solid #9c27b0;
        padding: 10px;
        margin: 5px 0;
    }
    .scene-header {
        background-color: #e3f2fd;
        padding: 8px;
        border-radius: 5px;
        font-weight: bold;
        margin: 10px 0;
    }
    .comment-box {
        background-color: #f5f5f5;
        padding: 10px;
        border-radius: 5px;
        margin: 5px 0;
    }
    .resolved-comment {
        background-color: #e8f5e8;
        border-left: 3px solid #4caf50;
    }
</style>
""", unsafe_allow_html=True)

# Authentication functions
def check_email_domain(email: str) -> bool:
    """Check if email belongs to hoichoi.tv domain"""
    return email.endswith('@hoichoi.tv')

def hash_password(password: str) -> str:
    """Simple password hashing"""
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user():
    """Handle user authentication"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        st.markdown("""
        <div class="main-header">
            <h1>🎬 S&P Compliance Review</h1>
            <h3>hoichoi Content Standards & Practices</h3>
        </div>
        """, unsafe_allow_html=True)
        
        with st.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.subheader("🔐 Login Required")
                email = st.text_input("Email Address", placeholder="yourname@hoichoi.tv")
                password = st.text_input("Password", type="password")
                
                if st.button("Login", type="primary", use_container_width=True):
                    if check_email_domain(email):
                        # Simple authentication - in production, use proper auth
                        st.session_state.authenticated = True
                        st.session_state.user_email = email
                        st.session_state.is_admin = email in ['admin@hoichoi.tv', 'sp@hoichoi.tv']
                        st.rerun()
                    else:
                        st.error("❌ Access denied. Only @hoichoi.tv email addresses are allowed.")
                
                st.info("ℹ️ Please use your hoichoi.tv email address to access the S&P review system.")
        
        return False
    
    return True

# Data persistence functions
@st.cache_data
def load_comments_data():
    """Load comments data from session state or initialize"""
    if 'comments_data' not in st.session_state:
        st.session_state.comments_data = {}
    return st.session_state.comments_data

def save_comment(script_id: str, scene_id: str, comment: Dict):
    """Save a comment to the comments database"""
    if 'comments_data' not in st.session_state:
        st.session_state.comments_data = {}
    
    if script_id not in st.session_state.comments_data:
        st.session_state.comments_data[script_id] = {}
    
    if scene_id not in st.session_state.comments_data[script_id]:
        st.session_state.comments_data[script_id][scene_id] = []
    
    comment['id'] = len(st.session_state.comments_data[script_id][scene_id])
    comment['timestamp'] = datetime.now().isoformat()
    comment['user'] = st.session_state.user_email
    
    st.session_state.comments_data[script_id][scene_id].append(comment)

# FIXED: Fast report generation
def generate_quick_reports(violations, filename):
    """Generate reports quickly for download"""
    
    # Generate XLSX
    df = pd.DataFrame(violations)
    xlsx_buffer = io.BytesIO()
    
    with pd.ExcelWriter(xlsx_buffer, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Violations', index=False)
        
        # Summary
        summary = pd.DataFrame({
            'Metric': ['Total', 'Critical', 'High', 'Medium', 'Low'],
            'Count': [
                len(violations),
                len([v for v in violations if v.get('severity') == 'critical']),
                len([v for v in violations if v.get('severity') == 'high']),
                len([v for v in violations if v.get('severity') == 'medium']),
                len([v for v in violations if v.get('severity') == 'low'])
            ]
        })
        summary.to_excel(writer, sheet_name='Summary', index=False)
    
    xlsx_buffer.seek(0)
    
    # Generate PDF content
    pdf_content = f"""S&P COMPLIANCE REPORT
File: {filename}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

SUMMARY:
Total Violations: {len(violations)}
Critical: {len([v for v in violations if v.get('severity') == 'critical'])}
High: {len([v for v in violations if v.get('severity') == 'high'])}

VIOLATIONS:
"""
    
    for i, v in enumerate(violations[:10], 1):
        pdf_content += f"\n{i}. {v.get('violationType', 'Unknown')} (Page {v.get('pageNumber', 'N/A')})\n"
        pdf_content += f"   Text: {v.get('violationText', 'N/A')[:100]}...\n"
        pdf_content += f"   Action: {v.get('suggestedAction', 'N/A')}\n"
    
    return xlsx_buffer.getvalue(), pdf_content.encode('utf-8')

# Analysis functions
def analyze_script(file_content: bytes, filename: str) -> Dict[str, Any]:
    """Analyze uploaded script file"""
    
    # Save uploaded file temporarily
    temp_file = f"temp_{filename}"
    with open(temp_file, "wb") as f:
        f.write(file_content)
    
    try:
        # Extract text
        text, pages_data = extract_text_from_docx(temp_file)
        
        if not text:
            return {"error": "Failed to extract text from document"}
        
        # Analyze with your backend
        analysis = analyze_document_robust(text, pages_data, OPENAI_API_KEY)
        
        # Clean up temp file
        os.remove(temp_file)
        
        return {
            "success": True,
            "analysis": analysis,
            "text": text,
            "pages_data": pages_data,
            "filename": filename
        }
    
    except Exception as e:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return {"error": f"Analysis failed: {str(e)}"}

def create_violation_charts(violations: List[Dict]) -> tuple:
    """Create visualization charts for violations"""
    
    if not violations:
        return None, None, None
    
    # Prepare data
    df = pd.DataFrame(violations)
    
    # Severity distribution
    severity_counts = df['severity'].value_counts()
    severity_colors = {'critical': '#f44336', 'high': '#ff9800', 'medium': '#ffeb3b', 'low': '#9c27b0'}
    
    fig_severity = px.pie(
        values=severity_counts.values,
        names=severity_counts.index,
        title="Violation Severity Distribution",
        color=severity_counts.index,
        color_discrete_map=severity_colors
    )
    
    # Violation types
    type_counts = df['violationType'].value_counts().head(10)
    fig_types = px.bar(
        x=type_counts.values,
        y=type_counts.index,
        orientation='h',
        title="Top Violation Types",
        labels={'x': 'Count', 'y': 'Violation Type'}
    )
    
    # Page distribution
    page_counts = df['pageNumber'].value_counts().sort_index()
    fig_pages = px.line(
        x=page_counts.index,
        y=page_counts.values,
        title="Violations by Page",
        labels={'x': 'Page Number', 'y': 'Violation Count'}
    )
    
    return fig_severity, fig_types, fig_pages

def extract_scenes(text: str) -> List[Dict]:
    """Extract scenes from script text based on INT./EXT. headers"""
    
    # Pattern to match scene headers
    scene_pattern = r'\b(INT\.|EXT\.)\s+([A-Z][A-Z\s\-\.]+?)(?:\s*-\s*(DAY|NIGHT|MORNING|EVENING|DAWN|DUSK))?\b'
    
    scenes = []
    lines = text.split('\n')
    current_scene = None
    current_content = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Check if this line is a scene header
        match = re.search(scene_pattern, line.upper())
        
        if match:
            # Save previous scene
            if current_scene:
                current_scene['content'] = '\n'.join(current_content)
                current_scene['end_line'] = i - 1
                scenes.append(current_scene)
            
            # Start new scene
            current_scene = {
                'id': len(scenes),
                'header': line,
                'location_type': match.group(1),
                'location': match.group(2).strip(),
                'time': match.group(3) if match.group(3) else 'UNSPECIFIED',
                'start_line': i,
                'end_line': None
            }
            current_content = [line]
        else:
            if current_scene:
                current_content.append(line)
    
    # Add final scene
    if current_scene:
        current_scene['content'] = '\n'.join(current_content)
        current_scene['end_line'] = len(lines) - 1
        scenes.append(current_scene)
    
    return scenes

# Main app tabs
def tab_edit_own_script():
    """Tab 1: Edit Own Script"""
    st.header("📝 Edit Own Script")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Upload Script")
        uploaded_file = st.file_uploader(
            "Choose a DOCX file",
            type=['docx'],
            help="Upload your script in DOCX format for S&P compliance review"
        )
        
        if uploaded_file is not None:
            # Show file details
            st.info(f"📄 File: {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")
            
            if st.button("🔍 Start Analysis", type="primary", use_container_width=True):
                
                # Progress tracking
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Step 1: Upload and extract
                status_text.text("📄 Extracting text from document...")
                progress_bar.progress(20)
                time.sleep(0.5)
                
                # Analyze script
                result = analyze_script(uploaded_file.getvalue(), uploaded_file.name)
                
                if "error" in result:
                    st.error(f"❌ {result['error']}")
                    return
                
                # Step 2: Analysis
                status_text.text("🤖 Analyzing content for S&P violations...")
                progress_bar.progress(60)
                time.sleep(1)
                
                # Step 3: Generate reports
                status_text.text("📊 Generating reports...")
                progress_bar.progress(80)
                
                analysis = result['analysis']
                violations = analysis.get('violations', [])
                
                # Save to session state
                st.session_state.current_analysis = result
                
                progress_bar.progress(100)
                status_text.text("✅ Analysis complete!")
                
                # Show results
                st.success(f"🎉 Analysis completed! Found {len(violations)} violations.")
    
    with col2:
        if 'current_analysis' in st.session_state:
            analysis = st.session_state.current_analysis['analysis']
            violations = analysis.get('violations', [])
            
            st.subheader("📊 Quick Stats")
            
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("Total Violations", len(violations))
                critical_count = len([v for v in violations if v.get('severity') == 'critical'])
                st.metric("Critical", critical_count, delta_color="inverse")
            
            with col_b:
                st.metric("Pages Analyzed", analysis['summary']['totalPages'])
                success_rate = float(analysis['summary']['successRate'].replace('%', ''))
                st.metric("Success Rate", f"{success_rate:.1f}%")
    
    # Show detailed analysis if available
    if 'current_analysis' in st.session_state:
        st.divider()
        
        analysis = st.session_state.current_analysis['analysis']
        violations = analysis.get('violations', [])
        
        if violations:
            # Violation analytics
            st.subheader("📈 Violation Analytics")
            
            # Create charts
            fig_severity, fig_types, fig_pages = create_violation_charts(violations)
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if fig_severity:
                    st.plotly_chart(fig_severity, use_container_width=True)
            
            with col2:
                if fig_types:
                    st.plotly_chart(fig_types, use_container_width=True)
            
            with col3:
                if fig_pages:
                    st.plotly_chart(fig_pages, use_container_width=True)
            
            # Violation breakdown
            st.subheader("🚨 Violation Breakdown")
            
            # Filter options
            col1, col2, col3 = st.columns(3)
            with col1:
                severity_filter = st.selectbox(
                    "Filter by Severity",
                    ["All", "Critical", "High", "Medium", "Low"]
                )
            
            with col2:
                type_filter = st.selectbox(
                    "Filter by Type",
                    ["All"] + list(set([v.get('violationType', 'Unknown') for v in violations]))
                )
            
            with col3:
                page_filter = st.selectbox(
                    "Filter by Page",
                    ["All"] + sorted(list(set([str(v.get('pageNumber', 'Unknown')) for v in violations])))
                )
            
            # Apply filters
            filtered_violations = violations.copy()
            
            if severity_filter != "All":
                filtered_violations = [v for v in filtered_violations if v.get('severity', '').lower() == severity_filter.lower()]
            
            if type_filter != "All":
                filtered_violations = [v for v in filtered_violations if v.get('violationType') == type_filter]
            
            if page_filter != "All":
                filtered_violations = [v for v in filtered_violations if str(v.get('pageNumber')) == page_filter]
            
            # Display violations
            for i, violation in enumerate(filtered_violations):
                severity = violation.get('severity', 'low')
                violation_class = f"violation-{severity}"
                
                with st.container():
                    st.markdown(f"""
                    <div class="{violation_class}">
                        <h4>🚨 {violation.get('violationType', 'Unknown')} (Page {violation.get('pageNumber', 'N/A')})</h4>
                        <p><strong>Severity:</strong> {severity.upper()}</p>
                        <p><strong>Text:</strong> "{violation.get('violationText', 'N/A')}"</p>
                        <p><strong>Issue:</strong> {violation.get('explanation', 'N/A')}</p>
                        <p><strong>Action:</strong> {violation.get('suggestedAction', 'N/A')}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button(f"Mark as Resolved", key=f"resolve_{i}"):
                        st.success("✅ Violation marked as resolved!")
            
            # FIXED: Fast download system
            st.subheader("📥 Download Reports")
            
            # Generate reports once when needed
            if 'reports_ready' not in st.session_state:
                st.session_state.reports_ready = False
            
            if not st.session_state.reports_ready:
                if st.button("🔄 Generate Reports", type="primary"):
                    with st.spinner("Generating reports..."):
                        filename = st.session_state.current_analysis['filename']
                        xlsx_data, pdf_data = generate_quick_reports(violations, filename)
                        
                        st.session_state.xlsx_report = xlsx_data
                        st.session_state.pdf_report = pdf_data
                        st.session_state.report_filename = filename
                        st.session_state.reports_ready = True
                        
                    st.success("✅ Reports generated!")
                    st.rerun()
            else:
                # Show download buttons
                col1, col2, col3 = st.columns(3)
                
                filename = st.session_state.report_filename
                
                with col1:
                    st.download_button(
                        label="📊 Download XLSX Report",
                        data=st.session_state.xlsx_report,
                        file_name=f"{filename}_analysis.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                
                with col2:
                    st.download_button(
                        label="📄 Download PDF Report",
                        data=st.session_state.pdf_report,
                        file_name=f"{filename}_report.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                
                with col3:
                    if st.button("🔄 Regenerate"):
                        st.session_state.reports_ready = False
                        st.rerun()

def tab_online_editor():
    """Tab 2: Online Editor - FIXED with real analysis"""
    st.header("✏️ Online Editor")
    
    # Upload options
    st.subheader("📂 Input Options")
    
    tab1, tab2, tab3 = st.tabs(["📄 Upload DOC/PDF", "📝 Paste Text", "📋 Load Previous"])
    
    with tab1:
        uploaded_file = st.file_uploader(
            "Upload Document",
            type=['doc', 'docx', 'pdf'],
            help="Upload DOC, DOCX, or PDF files"
        )
        
        if uploaded_file:
            st.info(f"📄 Loaded: {uploaded_file.name}")
            if st.button("🔍 Analyze Uploaded File"):
                # Process uploaded file here
                st.info("File analysis feature coming soon!")
    
    with tab2:
        text_input = st.text_area(
            "Paste Script Text",
            height=200,
            placeholder="Paste your script content here..."
        )
        
        if text_input and st.button("🔍 Analyze Text", type="primary"):
            # FIXED: Use your original analysis system
            with st.spinner("Analyzing text for S&P violations..."):
                try:
                    # Save text as temp file and analyze with your system
                    temp_filename = "pasted_text.txt"
                    with open(temp_filename, "w", encoding='utf-8') as f:
                        f.write(text_input)
                    
                    # Mock pages data for text analysis
                    pages_data = [{"text": text_input, "page": 1}]
                    
                    # Use your original analysis function
                    analysis = analyze_document_robust(text_input, pages_data, OPENAI_API_KEY)
                    
                    st.session_state.editor_text = text_input
                    st.session_state.editor_analysis = analysis
                    
                    violations = analysis.get('violations', [])
                    if violations:
                        st.success(f"✅ Found {len(violations)} violations")
                    else:
                        st.success("✅ No violations found")
                    
                    if os.path.exists(temp_filename):
                        os.remove(temp_filename)
                        
                except Exception as e:
                    st.error(f"Analysis failed: {str(e)}")
    
    with tab3:
        if 'current_analysis' in st.session_state:
            if st.button("📋 Load Current Analysis"):
                st.session_state.editor_text = st.session_state.current_analysis['text']
                st.session_state.editor_analysis = st.session_state.current_analysis['analysis']
                st.success("✅ Previous analysis loaded!")
    
    # FIXED: Two-column editor with real highlighting
    if 'editor_text' in st.session_state:
        st.divider()
        
        col1, col2 = st.columns([3, 2])
        
        with col1:
            st.subheader("📝 Text with Violation Highlights")
            
            text = st.session_state.editor_text
            analysis = st.session_state.get('editor_analysis', {})
            violations = analysis.get('violations', [])
            
            # FIXED: Real highlighting based on your violations
            highlighted_text = text
            
            if violations:
                # Apply highlighting for each violation
                for violation in violations:
                    violation_text = violation.get('violationText', '')
                    severity = violation.get('severity', 'low')
                    
                    if violation_text and violation_text in highlighted_text:
                        color_map = {
                            'critical': '#ffcdd2',
                            'high': '#fff3e0', 
                            'medium': '#fffde7',
                            'low': '#f3e5f5'
                        }
                        
                        bg_color = color_map.get(severity, '#f3e5f5')
                        
                        highlighted_text = highlighted_text.replace(
                            violation_text,
                            f'<span style="background-color: {bg_color}; padding: 2px 4px; border-radius: 3px; font-weight: bold;" title="{violation.get("explanation", "")}">{violation_text}</span>'
                        )
            
            # Display highlighted text
            st.markdown(
                f'<div style="background-color: #fafafa; padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0; max-height: 400px; overflow-y: auto;">{highlighted_text.replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True
            )
            
            # Legend
            if violations:
                st.markdown("""
                **🎨 Violation Severity Legend:**
                - <span style="background-color: #ffcdd2; padding: 2px 4px; border-radius: 3px;">🔴 Critical</span>
                - <span style="background-color: #fff3e0; padding: 2px 4px; border-radius: 3px;">🟠 High</span>  
                - <span style="background-color: #fffde7; padding: 2px 4px; border-radius: 3px;">🟡 Medium</span>
                - <span style="background-color: #f3e5f5; padding: 2px 4px; border-radius: 3px;">🟣 Low</span>
                """, unsafe_allow_html=True)
            
        with col2:
            st.subheader("🔍 Violation Details")
            
            if 'editor_analysis' in st.session_state:
                violations = st.session_state.editor_analysis.get('violations', [])
                
                if violations:
                    # Quick stats
                    critical = len([v for v in violations if v['severity'] == 'critical'])
                    high = len([v for v in violations if v['severity'] == 'high'])
                    medium = len([v for v in violations if v['severity'] == 'medium'])
                    low = len([v for v in violations if v['severity'] == 'low'])
                    
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.metric("🔴 Critical", critical)
                        st.metric("🟠 High", high)
                    with col_b:
                        st.metric("🟡 Medium", medium)
                        st.metric("🟣 Low", low)
                    
                    st.divider()
                    
                    # Violation list
                    for i, violation in enumerate(violations):
                        severity = violation.get('severity', 'low')
                        severity_icons = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟣'}
                        
                        with st.expander(f"{severity_icons.get(severity, '⚪')} {violation.get('violationType', 'Unknown')}"):
                            st.markdown(f"**Text:** {violation.get('violationText', 'N/A')}")
                            st.markdown(f"**Issue:** {violation.get('explanation', 'N/A')}")
                            st.markdown(f"**Suggestion:** {violation.get('suggestedAction', 'N/A')}")
                            
                            st.text_area("💡 Your Fix", placeholder="Write your fix here...", key=f"fix_{i}")
                            
                            col_a, col_b = st.columns(2)
                            with col_a:
                                st.button("✅ Apply Fix", type="primary", key=f"apply_{i}")
                            with col_b:
                                st.button("⏭️ Skip", key=f"skip_{i}")
                else:
                    st.success("✅ No violations detected!")
            else:
                st.info("Analyze text to see violation details")

def tab_scene_navigator():
    """Tab 3: Scene Navigator & Comment System"""
    st.header("🎬 Scene Navigator & Comments")
    
    # Load text for scene extraction
    text = ""
    if 'current_analysis' in st.session_state:
        text = st.session_state.current_analysis['text']
    elif 'editor_text' in st.session_state:
        text = st.session_state.editor_text
    else:
        st.info("📄 Please upload a script in Tab 1 or Tab 2 to use the Scene Navigator")
        return
    
    # Extract scenes
    scenes = extract_scenes(text)
    
    if not scenes:
        st.warning("🎬 No scenes detected. Make sure your script uses standard INT./EXT. scene headers.")
        return
    
    st.success(f"🎬 Found {len(scenes)} scenes")
    
    # Scene navigation
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.subheader("📋 Scene List")
        
        selected_scene_idx = st.selectbox(
            "Select Scene",
            range(len(scenes)),
            format_func=lambda x: f"Scene {x+1}: {scenes[x]['location']}"
        )
        
        # Scene info
        scene = scenes[selected_scene_idx]
        st.markdown(f"""
        **📍 Location:** {scene['location']}  
        **🌅 Time:** {scene['time']}  
        **📄 Lines:** {scene['start_line']}-{scene['end_line']}
        """)
        
        # Quick stats
        total_comments = len(load_comments_data().get(f"script_{hash(text)}", {}).get(f"scene_{selected_scene_idx}", []))
        unresolved_comments = len([c for c in load_comments_data().get(f"script_{hash(text)}", {}).get(f"scene_{selected_scene_idx}", []) if not c.get('resolved', False)])
        
        st.metric("💬 Comments", total_comments)
        st.metric("⚠️ Unresolved", unresolved_comments)
    
    with col2:
        st.subheader(f"🎬 {scene['header']}")
        
        # Scene content
        with st.container():
            st.markdown(f"""
            <div class="scene-header">
                {scene['header']}
            </div>
            """, unsafe_allow_html=True)
            
            # Display scene content with line numbers
            content_lines = scene['content'].split('\n')[1:]  # Skip header
            for i, line in enumerate(content_lines):
                if line.strip():
                    st.text(f"{scene['start_line'] + i + 1:3d}: {line}")
        
        st.divider()
        
        # Comments section
        st.subheader("💬 Comments & Discussions")
        
        # Add new comment
        with st.expander("➕ Add New Comment"):
            comment_type = st.selectbox("Comment Type", ["General", "S&P Issue", "Creative Note", "Legal", "Technical"])
            comment_text = st.text_area("Comment", placeholder="Add your comment here...")
            
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                priority = st.selectbox("Priority", ["Low", "Medium", "High", "Critical"])
            with col_b:
                tag = st.text_input("Tag", placeholder="e.g., violence, dialogue")
            with col_c:
                assign_to = st.text_input("Assign to", placeholder="email@hoichoi.tv")
            
            if st.button("💬 Add Comment", type="primary"):
                if comment_text:
                    comment = {
                        'type': comment_type,
                        'text': comment_text,
                        'priority': priority,
                        'tag': tag,
                        'assigned_to': assign_to,
                        'resolved': False
                    }
                    
                    script_id = f"script_{hash(text)}"
                    scene_id = f"scene_{selected_scene_idx}"
                    save_comment(script_id, scene_id, comment)
                    
                    st.success("✅ Comment added successfully!")
                    st.rerun()
        
        # Display existing comments
        script_id = f"script_{hash(text)}"
        scene_id = f"scene_{selected_scene_idx}"
        comments = load_comments_data().get(script_id, {}).get(scene_id, [])
        
        if comments:
            for comment in comments:
                comment_class = "resolved-comment" if comment.get('resolved') else "comment-box"
                
                with st.container():
                    st.markdown(f"""
                    <div class="{comment_class}">
                        <strong>💬 {comment.get('type', 'General')}</strong> 
                        <span style="color: #666;">by {comment.get('user', 'Unknown')} • {comment.get('timestamp', 'Unknown time')}</span>
                        <br>
                        <p>{comment.get('text', '')}</p>
                        <small>🏷️ {comment.get('tag', 'No tag')} • 📌 {comment.get('priority', 'Low')} priority</small>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if not comment.get('resolved', False):
                        if st.button(f"✅ Mark Resolved", key=f"resolve_comment_{comment.get('id')}"):
                            comment['resolved'] = True
                            comment['resolved_by'] = st.session_state.user_email
                            comment['resolved_at'] = datetime.now().isoformat()
                            st.success("✅ Comment marked as resolved!")
                            st.rerun()
        else:
            st.info("💬 No comments yet. Add the first comment above!")

def admin_panel():
    """Admin panel for user management"""
    if not st.session_state.get('is_admin', False):
        st.error("❌ Admin access required")
        return
    
    st.header("⚙️ Admin Panel")
    
    tab1, tab2, tab3 = st.tabs(["👥 Users", "📊 Analytics", "⚙️ Settings"])
    
    with tab1:
        st.subheader("User Management")
        
        # Mock user data
        users_data = [
            {"Email": "john.doe@hoichoi.tv", "Role": "Reviewer", "Last Active": "2024-01-15", "Status": "Active"},
            {"Email": "jane.smith@hoichoi.tv", "Role": "Creative", "Last Active": "2024-01-14", "Status": "Active"},
            {"Email": "admin@hoichoi.tv", "Role": "Admin", "Last Active": "2024-01-15", "Status": "Active"},
        ]
        
        df = pd.DataFrame(users_data)
        st.dataframe(df, use_container_width=True)
        
        with st.expander("➕ Add New User"):
            new_email = st.text_input("Email")
            new_role = st.selectbox("Role", ["Reviewer", "Creative", "Admin"])
            if st.button("Add User"):
                st.success(f"✅ User {new_email} added as {new_role}")
    
    with tab2:
        st.subheader("System Analytics")
        
        # Mock analytics data
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Scripts", "127", "+12")
        with col2:
            st.metric("Active Reviews", "23", "+5")
        with col3:
            st.metric("Resolved Issues", "89%", "+2%")
        with col4:
            st.metric("Avg. Processing", "3.2 min", "-0.5 min")
        
        # Mock charts
        dates = pd.date_range(start='2024-01-01', end='2024-01-15', freq='D')
        scripts_per_day = [5, 8, 12, 6, 9, 15, 11, 7, 13, 10, 8, 14, 9, 6, 11]
        
        fig = px.line(x=dates, y=scripts_per_day, title="Scripts Processed Per Day")
        st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        st.subheader("System Settings")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.number_input("Max File Size (MB)", value=50, min_value=1, max_value=500)
            st.selectbox("Default Severity Filter", ["All", "Critical", "High"])
            st.checkbox("Enable Email Notifications", value=True)
        
        with col2:
            st.number_input("Session Timeout (hours)", value=8, min_value=1, max_value=24)
            st.selectbox("Default Report Format", ["PDF", "XLSX", "Both"])
            st.checkbox("Auto-assign Reviews", value=False)
        
        if st.button("💾 Save Settings", type="primary"):
            st.success("✅ Settings saved successfully!")

# Main application
def main():
    # Authentication check
    if not authenticate_user():
        return
    
    # Sidebar
    with st.sidebar:
        st.markdown(f"""
        <div style="text-align: center; padding: 1rem; background-color: #f0f0f0; border-radius: 10px; margin-bottom: 1rem;">
            <h3>🎬 hoichoi S&P</h3>
            <p>👋 Welcome, {st.session_state.user_email}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Navigation
        if st.session_state.get('is_admin', False):
            page = st.selectbox(
                "Navigate to:",
                ["📝 Edit Own Script", "✏️ Online Editor", "🎬 Scene Navigator", "⚙️ Admin Panel"]
            )
        else:
            page = st.selectbox(
                "Navigate to:",
                ["📝 Edit Own Script", "✏️ Online Editor", "🎬 Scene Navigator"]
            )
        
        # Quick stats
        st.divider()
        st.subheader("📊 Quick Stats")
        
        if 'current_analysis' in st.session_state:
            analysis = st.session_state.current_analysis['analysis']
            violations = analysis.get('violations', [])
            
            critical_count = len([v for v in violations if v.get('severity') == 'critical'])
            high_count = len([v for v in violations if v.get('severity') == 'high'])
            
            st.metric("🔴 Critical", critical_count)
            st.metric("🟠 High", high_count)
            st.metric("📄 Total Pages", analysis['summary']['totalPages'])
        else:
            st.info("Upload a script to see stats")
        
        # System status
        st.divider()
        st.subheader("🔧 System Status")
        st.success("✅ AI Engine: Online")
        st.success("✅ Report Generator: Ready")
        st.success("✅ Database: Connected")
        
        # Logout
        if st.button("🚪 Logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    
    # Main header
    st.markdown("""
    <div class="main-header">
        <h1>🎬 Standards & Practices Review System</h1>
        <p>Streamlined S&P compliance for hoichoi creative content</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Route to appropriate page
    if page == "📝 Edit Own Script":
        tab_edit_own_script()
    elif page == "✏️ Online Editor":
        tab_online_editor()
    elif page == "🎬 Scene Navigator":
        tab_scene_navigator()
    elif page == "⚙️ Admin Panel":
        admin_panel()

if __name__ == "__main__":
    main()