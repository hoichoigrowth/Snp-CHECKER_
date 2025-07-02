import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os
import time
from datetime import datetime
import re
import io
import hashlib
from typing import Dict, List, Any

# Import optional dependencies with error handling
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import Color, red, orange, yellow, lightgrey, black
    from reportlab.lib.units import inch
    from reportlab.platypus.flowables import KeepTogether
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# Configuration
MAX_CHARS_PER_CHUNK = 4000
OVERLAP_CHARS = 200
MAX_TOKENS_OUTPUT = 1000
CHUNK_DELAY = 1
MAX_RETRIES = 3

# S&P Violation Rules
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

# Streamlit App Configuration
st.set_page_config(
    page_title="S&P Compliance Analyzer",
    page_icon="🔍",
    layout="wide"
)

def get_api_key():
    """Get OpenAI API key from Streamlit secrets or user input"""
    try:
        return st.secrets.get("OPENAI_API_KEY", None)
    except:
        return None

def extract_text_from_docx_bytes(file_bytes):
    """Extract text from uploaded DOCX file bytes"""
    if not DOCX_AVAILABLE:
        st.error("❌ python-docx not available. Please check requirements.txt")
        return None, []
    
    try:
        doc = Document(io.BytesIO(file_bytes))
        pages_data = []
        full_text = ""
        
        page_num = 1
        current_page_text = ""
        char_count = 0
        
        for para in doc.paragraphs:
            para_text = para.text
            
            if para_text.strip():
                current_page_text += para_text + "\n"
                char_count += len(para_text) + 1
                
                if char_count > 2000:
                    pages_data.append({
                        'page_number': page_num,
                        'text': current_page_text.strip()
                    })
                    full_text += f"\n=== PAGE {page_num} ===\n{current_page_text}\n"
                    
                    page_num += 1
                    current_page_text = ""
                    char_count = 0
        
        if current_page_text.strip():
            pages_data.append({
                'page_number': page_num,
                'text': current_page_text.strip()
            })
            full_text += f"\n=== PAGE {page_num} ===\n{current_page_text}\n"
        
        return full_text, pages_data
        
    except Exception as e:
        st.error(f"Error extracting text: {e}")
        return None, []

def chunk_text(text, max_chars=MAX_CHARS_PER_CHUNK):
    """Split text into analysis chunks"""
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    start = 0
    overlap = OVERLAP_CHARS
    
    while start < len(text):
        end = start + max_chars
        
        if end < len(text):
            # Find good break points
            break_points = ['\n=== PAGE', '.\n', '. ', '\n\n', '\n', ' ']
            best_break = end
            
            for break_point in break_points:
                search_start = max(start + max_chars // 2, end - 500)
                last_break = text.rfind(break_point, search_start, end)
                
                if last_break > search_start:
                    best_break = last_break + len(break_point)
                    break
            
            end = best_break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        start = end - overlap
        if start >= len(text):
            break
    
    return chunks

def create_analysis_prompt():
    """Create S&P compliance analysis prompt"""
    violation_types = []
    for v_type, details in VIOLATION_RULES.items():
        violation_types.append(f"- {v_type.replace('_', ' ')}: {details['description']} (Severity: {details['severity']})")
    
    violation_types_str = "\n".join(violation_types)
    
    return f"""You are an expert S&P compliance reviewer for Indian digital media. Analyze this content chunk for violations.

VIOLATION CATEGORIES (choose most appropriate):
{violation_types_str}

CRITICAL INSTRUCTIONS:
1. Copy violation text EXACTLY as it appears
2. Extract meaningful violations only (minimum 10 characters)
3. Choose appropriate category and severity
4. Focus on substantial policy violations

Return ONLY valid JSON:
{{
  "violations": [
    {{
      "violationText": "EXACT text preserving all formatting",
      "violationType": "Category name from list above",
      "explanation": "why this violates broadcasting standards",
      "suggestedAction": "specific remediation needed",
      "severity": "critical|high|medium|low"
    }}
  ]
}}

If no violations found, return: {{"violations": []}}"""

def analyze_chunk(chunk, chunk_num, total_chunks, api_key):
    """Analyze single chunk with OpenAI"""
    if not OPENAI_AVAILABLE or not api_key:
        return {"violations": []}
    
    try:
        client = OpenAI(api_key=api_key)
        
        prompt = create_analysis_prompt()
        full_prompt = f"""{prompt}

Content to analyze:
{chunk}

JSON response only:"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an S&P compliance expert. Return only valid JSON."},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.1,
            max_tokens=MAX_TOKENS_OUTPUT,
            timeout=60
        )
        
        result = response.choices[0].message.content.strip()
        
        # Parse JSON with fallback
        try:
            parsed_result = json.loads(result)
        except json.JSONDecodeError:
            json_start = result.find('{')
            json_end = result.rfind('}')
            if json_start != -1 and json_end != -1:
                json_text = result[json_start:json_end + 1]
                try:
                    parsed_result = json.loads(json_text)
                except:
                    return {"violations": []}
            else:
                return {"violations": []}
        
        # Validate violations
        if 'violations' in parsed_result:
            enhanced_violations = []
            for violation in parsed_result['violations']:
                violation_text = violation.get('violationText', '').strip()
                if len(violation_text) >= 10:
                    enhanced_violations.append(violation)
            parsed_result['violations'] = enhanced_violations
        
        time.sleep(CHUNK_DELAY)
        return parsed_result
        
    except Exception as e:
        st.error(f"Error analyzing chunk {chunk_num}: {e}")
        return {"violations": []}

def find_page_number(violation_text, pages_data):
    """Find which page contains the violation"""
    for page_data in pages_data:
        if violation_text in page_data['text']:
            return page_data['page_number']
    
    # Fuzzy matching
    search_text = violation_text[:50] if len(violation_text) > 50 else violation_text
    for page_data in pages_data:
        if search_text in page_data['text']:
            return page_data['page_number']
    
    return 1

def analyze_document(text, pages_data, api_key):
    """Analyze entire document"""
    if not text or not api_key:
        return {"violations": [], "summary": {}}
    
    chunks = chunk_text(text)
    all_violations = []
    successful_chunks = 0
    
    # Progress tracking
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, chunk in enumerate(chunks):
        progress = (i + 1) / len(chunks)
        progress_bar.progress(progress)
        status_text.text(f"Analyzing chunk {i+1}/{len(chunks)}...")
        
        analysis = analyze_chunk(chunk, i+1, len(chunks), api_key)
        
        if 'violations' in analysis:
            for violation in analysis['violations']:
                violation['pageNumber'] = find_page_number(violation.get('violationText', ''), pages_data)
                violation['chunkNumber'] = i + 1
                all_violations.append(violation)
            successful_chunks += 1
    
    progress_bar.progress(1.0)
    status_text.text("✅ Analysis complete!")
    
    # Remove duplicates
    unique_violations = []
    seen_texts = set()
    for violation in all_violations:
        v_text = violation.get('violationText', '')
        duplicate_key = (v_text[:100], violation.get('violationType', ''), violation.get('pageNumber', 0))
        
        if duplicate_key not in seen_texts:
            seen_texts.add(duplicate_key)
            unique_violations.append(violation)
    
    # Sort by page and severity
    severity_order = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}
    unique_violations.sort(key=lambda x: (
        x.get('pageNumber', 0),
        -severity_order.get(x.get('severity', 'low'), 1)
    ))
    
    return {
        "violations": unique_violations,
        "summary": {
            "totalViolations": len(unique_violations),
            "totalPages": len(pages_data),
            "chunksAnalyzed": len(chunks),
            "successfulChunks": successful_chunks,
            "successRate": f"{(successful_chunks/len(chunks)*100):.1f}%" if chunks else "0%"
        }
    }

def generate_excel_report(violations, filename):
    """Generate Excel report"""
    if not EXCEL_AVAILABLE:
        return None
    
    try:
        df = pd.DataFrame(violations)
        buffer = io.BytesIO()
        
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Violations', index=False)
            
            # Summary sheet
            summary_data = {
                'Metric': ['Total Violations', 'Critical', 'High', 'Medium', 'Low'],
                'Count': [
                    len(violations),
                    len([v for v in violations if v.get('severity') == 'critical']),
                    len([v for v in violations if v.get('severity') == 'high']),
                    len([v for v in violations if v.get('severity') == 'medium']),
                    len([v for v in violations if v.get('severity') == 'low'])
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        st.error(f"Error generating Excel report: {e}")
        return None

def generate_violations_report_pdf(violations, filename):
    """Generate PDF report with violation details"""
    if not PDF_AVAILABLE:
        return None
    
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
        
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontSize=18,
            spaceAfter=30,
            textColor=Color(0.2, 0.2, 0.6),
            alignment=1
        )
        
        story.append(Paragraph("S&P COMPLIANCE VIOLATION REPORT", title_style))
        story.append(Paragraph(f"Document: {filename}", styles['Normal']))
        story.append(Paragraph(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Paragraph(f"Total Violations: {len(violations)}", styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Summary by severity
        severity_counts = {}
        for v in violations:
            severity = v.get('severity', 'medium')
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        story.append(Paragraph("VIOLATION SUMMARY BY SEVERITY", styles['Heading2']))
        for severity in ['critical', 'high', 'medium', 'low']:
            count = severity_counts.get(severity, 0)
            if count > 0:
                color = red if severity == 'critical' else orange if severity == 'high' else Color(0.7, 0.7, 0) if severity == 'medium' else Color(0.5, 0.5, 0.5)
                severity_style = ParagraphStyle('Severity', parent=styles['Normal'], textColor=color, fontSize=12, spaceAfter=6)
                story.append(Paragraph(f"• {severity.upper()}: {count} violations", severity_style))
        
        story.append(Spacer(1, 20))
        
        # Detailed violations
        story.append(Paragraph("DETAILED VIOLATIONS", styles['Heading1']))
        story.append(Spacer(1, 10))
        
        for i, violation in enumerate(violations, 1):
            # Violation header
            violation_style = ParagraphStyle(
                f'Violation{i}',
                parent=styles['Normal'],
                leftIndent=20,
                rightIndent=20,
                spaceBefore=10,
                spaceAfter=10,
                borderWidth=1,
                borderColor=Color(0.8, 0.8, 0.8),
                backColor=Color(0.98, 0.98, 0.98)
            )
            
            severity = violation.get('severity', 'medium')
            severity_color = red if severity == 'critical' else orange if severity == 'high' else Color(0.7, 0.7, 0) if severity == 'medium' else Color(0.5, 0.5, 0.5)
            
            violation_detail = f"<b>#{i}</b><br/>"
            violation_detail += f"<b>Type:</b> {violation.get('violationType', 'Unknown')}<br/>"
            violation_detail += f"<b>Page:</b> {violation.get('pageNumber', 'N/A')}<br/>"
            violation_detail += f"<b>Severity:</b> <font color='{severity_color}'>{severity.upper()}</font><br/>"
            violation_detail += f"<b>Violation Text:</b><br/><font color='red'><b>{violation.get('violationText', 'N/A')}</b></font><br/>"
            violation_detail += f"<b>Explanation:</b> {violation.get('explanation', 'N/A')}<br/>"
            violation_detail += f"<b>Suggested Action:</b> {violation.get('suggestedAction', 'N/A')}<br/>"
            violation_detail += f"<b>Status:</b> <font color='red'>PENDING REVIEW</font>"
            
            story.append(Paragraph(violation_detail, violation_style))
        
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        st.error(f"Error generating violations report PDF: {e}")
        return None

def generate_highlighted_text_pdf(text, violations, filename):
    """Generate PDF with original text and highlighted violations"""
    if not PDF_AVAILABLE:
        return None
    
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
        
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontSize=18,
            spaceAfter=30,
            textColor=Color(0.2, 0.2, 0.6),
            alignment=1
        )
        
        story.append(Paragraph("S&P COMPLIANCE - HIGHLIGHTED TEXT", title_style))
        story.append(Paragraph(f"Document: {filename}", styles['Normal']))
        story.append(Paragraph(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Legend
        story.append(Paragraph("COLOR LEGEND", styles['Heading2']))
        legend_text = """
        <b>Background Colors indicate violation severity:</b><br/>
        🔴 <font color="red">Critical Severity</font> - Red background, immediate attention required<br/>
        🟠 <font color="orange">High Severity</font> - Orange background, high priority review<br/>
        🟡 <font color="#B8860B">Medium Severity</font> - Yellow background, standard review<br/>
        🟣 <font color="purple">Low Severity</font> - Purple background, minor issues<br/><br/>
        <b><font color="red">Bold red text indicates the exact violation content</font></b> that triggered the S&P flag.
        """
        story.append(Paragraph(legend_text, styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Create violation mapping for highlighting
        violation_map = {}
        for violation in violations:
            v_text = violation.get('violationText', '').strip()
            severity = violation.get('severity', 'medium').lower()
            
            if v_text and len(v_text) >= 10:
                violation_map[v_text] = {
                    'severity': severity,
                    'type': violation.get('violationType', 'Unknown'),
                    'explanation': violation.get('explanation', '')
                }
        
        # Process text with highlighting
        story.append(Paragraph("DOCUMENT TEXT WITH HIGHLIGHTED VIOLATIONS", styles['Heading1']))
        story.append(Spacer(1, 10))
        
        # Split text into paragraphs
        paragraphs = text.split('\n')
        
        for para_text in paragraphs:
            if para_text.strip():
                # Skip page markers
                if '=== PAGE' in para_text:
                    continue
                
                # Check for violations in this paragraph
                highlighted_text = para_text
                has_violation = False
                
                # Sort violations by length (longest first) to avoid overlapping replacements
                sorted_violations = sorted(violation_map.items(), key=lambda x: len(x[0]), reverse=True)
                
                for v_text, v_info in sorted_violations:
                    if v_text in highlighted_text:
                        severity = v_info['severity']
                        
                        # Color mapping
                        if severity == 'critical':
                            bg_color = '#ffcdd2'  # Light red
                        elif severity == 'high':
                            bg_color = '#fff3e0'  # Light orange
                        elif severity == 'medium':
                            bg_color = '#fffde7'  # Light yellow
                        else:
                            bg_color = '#f3e5f5'  # Light purple
                        
                        # Escape XML characters in violation text
                        safe_v_text = v_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                        
                        # Replace with highlighted version
                        highlighted_replacement = f'<span style="background-color: {bg_color}; padding: 2px;"><font color="red"><b>{safe_v_text}</b></font></span>'
                        highlighted_text = highlighted_text.replace(v_text, highlighted_replacement)
                        has_violation = True
                
                # Add paragraph
                if has_violation:
                    # Highlighted paragraph style
                    highlighted_style = ParagraphStyle(
                        'HighlightedPara',
                        parent=styles['Normal'],
                        spaceBefore=6,
                        spaceAfter=6,
                        leftIndent=10,
                        rightIndent=10
                    )
                    story.append(Paragraph(highlighted_text, highlighted_style))
                else:
                    # Normal paragraph
                    if len(para_text) > 800:  # Truncate very long paragraphs
                        para_text = para_text[:800] + "..."
                    story.append(Paragraph(para_text, styles['Normal']))
                
                story.append(Spacer(1, 4))
        
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        st.error(f"Error generating highlighted text PDF: {e}")
        return None

def create_violation_charts(violations):
    """Create visualization charts"""
    if not violations:
        return None, None
    
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
    
    return fig_severity, fig_types

def main():
    # Header
    st.title("🔍 S&P Compliance Analyzer")
    st.markdown("**Standards & Practices Compliance Checker for Digital Media**")
    
    # System status in sidebar
    with st.sidebar:
        st.header("🔧 System Status")
        if OPENAI_AVAILABLE:
            st.success("✅ OpenAI: Available")
        else:
            st.error("❌ OpenAI: Missing")
        
        if DOCX_AVAILABLE:
            st.success("✅ DOCX Processing: Available")
        else:
            st.error("❌ DOCX Processing: Missing")
        
        if EXCEL_AVAILABLE:
            st.success("✅ Excel Reports: Available")
        else:
            st.error("❌ Excel Reports: Missing")
        
        if PDF_AVAILABLE:
            st.success("✅ PDF Generation: Available")
        else:
            st.error("❌ PDF Generation: Missing")
    
    # API Key
    api_key = get_api_key()
    
    if not api_key:
        st.warning("⚠️ OpenAI API key not configured!")
        st.info("Please add OPENAI_API_KEY to Streamlit secrets or environment variables.")
        api_key = st.text_input("Enter OpenAI API Key", type="password", help="Your OpenAI API key for content analysis")
        if not api_key:
            st.stop()
    else:
        st.success("🔑 API Key configured")
    
    # Main tabs for upload vs paste
    tab1, tab2 = st.tabs(["📤 Upload Document", "📝 Paste Text"])
    
    with tab1:
        st.header("📤 Upload Document Analysis")
        uploaded_file = st.file_uploader(
            "Choose a DOCX file",
            type=['docx'],
            help="Upload a Microsoft Word document for S&P compliance analysis"
        )
        
        if uploaded_file is not None:
            st.success(f"✅ File uploaded: {uploaded_file.name} ({uploaded_file.size/1024:.1f} KB)")
            
            if st.button("🔍 Start Analysis", type="primary", key="upload_analyze"):
                # Extract text
                with st.spinner("📄 Extracting text from document..."):
                    text, pages_data = extract_text_from_docx_bytes(uploaded_file.getvalue())
                
                if not text:
                    st.error("❌ Failed to extract text from document")
                    return
                
                st.success(f"✅ Extracted {len(text):,} characters from {len(pages_data)} pages")
                
                # Analyze document
                st.header("🤖 Analysis in Progress")
                analysis = analyze_document(text, pages_data, api_key)
                
                violations = analysis.get('violations', [])
                summary = analysis.get('summary', {})
                
                # Results
                st.header("📊 Analysis Results")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Violations", summary.get('totalViolations', 0))
                with col2:
                    critical_count = len([v for v in violations if v.get('severity') == 'critical'])
                    st.metric("🔴 Critical", critical_count)
                with col3:
                    st.metric("📄 Pages", summary.get('totalPages', 0))
                with col4:
                    st.metric("✅ Success Rate", summary.get('successRate', '0%'))
                
                if violations:
                    # Charts
                    st.subheader("📈 Violation Analytics")
                    fig_severity, fig_types = create_violation_charts(violations)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if fig_severity:
                            st.plotly_chart(fig_severity, use_container_width=True)
                    
                    with col2:
                        if fig_types:
                            st.plotly_chart(fig_types, use_container_width=True)
                    
                    # Violation details
                    st.subheader(f"🚨 Violations Found: {len(violations)}")
                    
                    for i, violation in enumerate(violations[:10]):  # Show first 10
                        severity = violation.get('severity', 'low')
                        
                        if severity == 'critical':
                            st.error(f"🔴 **{violation.get('violationType', 'Unknown')}** (Page {violation.get('pageNumber', 'N/A')})")
                        elif severity == 'high':
                            st.warning(f"🟠 **{violation.get('violationType', 'Unknown')}** (Page {violation.get('pageNumber', 'N/A')})")
                        elif severity == 'medium':
                            st.info(f"🟡 **{violation.get('violationType', 'Unknown')}** (Page {violation.get('pageNumber', 'N/A')})")
                        else:
                            st.success(f"🟢 **{violation.get('violationType', 'Unknown')}** (Page {violation.get('pageNumber', 'N/A')})")
                        
                        st.write(f"**Violated Text:** \"{violation.get('violationText', 'N/A')[:200]}...\"")
                        st.write(f"**Issue:** {violation.get('explanation', 'N/A')}")
                        st.write(f"**Action:** {violation.get('suggestedAction', 'N/A')}")
                        st.divider()
                    
                    if len(violations) > 10:
                        st.info(f"Showing first 10 of {len(violations)} total violations")
                    
                    # Generate all reports
                    st.subheader("📥 Download Reports")
                    
                    with st.spinner("Generating reports..."):
                        # Excel report
                        excel_data = generate_excel_report(violations, uploaded_file.name)
                        
                        # PDF reports
                        violations_report_pdf = generate_violations_report_pdf(violations, uploaded_file.name)
                        highlighted_text_pdf = generate_highlighted_text_pdf(text, violations, uploaded_file.name)
                    
                    # Download buttons
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if excel_data:
                            st.download_button(
                                label="📊 Download Excel Report",
                                data=excel_data,
                                file_name=f"{uploaded_file.name}_analysis.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
                    
                    with col2:
                        if violations_report_pdf:
                            st.download_button(
                                label="📋 Download Violations Report PDF",
                                data=violations_report_pdf,
                                file_name=f"{uploaded_file.name}_violations_report.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                    
                    with col3:
                        if highlighted_text_pdf:
                            st.download_button(
                                label="🎨 Download Highlighted Text PDF",
                                data=highlighted_text_pdf,
                                file_name=f"{uploaded_file.name}_highlighted_text.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                    
                    if not all([excel_data, violations_report_pdf, highlighted_text_pdf]):
                        st.warning("⚠️ Some reports could not be generated. Check system status in sidebar.")
                
                else:
                    st.success("🎉 No violations found! Content appears to comply with S&P standards.")
    
    with tab2:
        st.header("📝 Paste Text Analysis")
        
        text_input = st.text_area(
            "Paste your content here",
            height=300,
            placeholder="Paste your script, dialogue, or content here for immediate S&P compliance analysis..."
        )
        
        if text_input and st.button("🔍 Analyze Text", type="primary", key="paste_analyze"):
            # Create mock pages data for pasted text
            pages_data = [{"page_number": 1, "text": text_input}]
            
            # Analyze pasted text
            st.header("🤖 Analyzing Pasted Text")
            analysis = analyze_document(text_input, pages_data, api_key)
            
            violations = analysis.get('violations', [])
            
            # Results for pasted text
            st.header("📊 Analysis Results")
            
            if violations:
                st.error(f"🚨 Found {len(violations)} violations in your text!")
                
                # Show violations with exact context
                st.subheader("🔍 Violated Strings with Context")
                
                for i, violation in enumerate(violations, 1):
                    severity = violation.get('severity', 'low')
                    
                    # Color-coded violation display
                    if severity == 'critical':
                        st.error(f"**🔴 Violation #{i}: {violation.get('violationType', 'Unknown')}**")
                    elif severity == 'high':
                        st.warning(f"**🟠 Violation #{i}: {violation.get('violationType', 'Unknown')}**")
                    elif severity == 'medium':
                        st.info(f"**🟡 Violation #{i}: {violation.get('violationType', 'Unknown')}**")
                    else:
                        st.success(f"**🟢 Violation #{i}: {violation.get('violationType', 'Unknown')}**")
                    
                    # Show violated text with highlighting
                    violated_text = violation.get('violationText', '')
                    
                    # Create highlighted version of the original text
                    highlighted_context = text_input
                    if violated_text in highlighted_context:
                        if severity == 'critical':
                            color = "#ffcdd2"
                        elif severity == 'high':
                            color = "#fff3e0"
                        elif severity == 'medium':
                            color = "#fffde7"
                        else:
                            color = "#f3e5f5"
                        
                        # Highlight the violated text
                        highlighted_context = highlighted_context.replace(
                            violated_text,
                            f'<span style="background-color: {color}; padding: 2px 4px; border-radius: 3px; font-weight: bold; color: red;">{violated_text}</span>'
                        )
                    
                    # Show context around violation
                    st.markdown("**Violated Text:**")
                    st.markdown(f'<div style="background-color: #fafafa; padding: 10px; border-radius: 5px; border-left: 3px solid red;"><b style="color: red;">"{violated_text}"</b></div>', unsafe_allow_html=True)
                    
                    st.markdown("**Context in Original Text:**")
                    st.markdown(f'<div style="background-color: #fafafa; padding: 10px; border-radius: 5px; max-height: 200px; overflow-y: auto;">{highlighted_context}</div>', unsafe_allow_html=True)
                    
                    st.markdown(f"**Why this violates S&P standards:** {violation.get('explanation', 'N/A')}")
                    st.markdown(f"**Suggested action:** {violation.get('suggestedAction', 'N/A')}")
                    st.markdown(f"**Severity:** {severity.upper()}")
                    
                    st.divider()
                
                # Show severity summary
                st.subheader("📊 Violation Summary")
                severity_counts = {}
                for v in violations:
                    severity = v.get('severity', 'medium')
                    severity_counts[severity] = severity_counts.get(severity, 0) + 1
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("🔴 Critical", severity_counts.get('critical', 0))
                with col2:
                    st.metric("🟠 High", severity_counts.get('high', 0))
                with col3:
                    st.metric("🟡 Medium", severity_counts.get('medium', 0))
                with col4:
                    st.metric("🟢 Low", severity_counts.get('low', 0))
                
            else:
                st.success("🎉 No violations found! Your text appears to comply with S&P standards.")
                st.balloons()
    
    # Footer with violation rules
    with st.expander("📋 S&P Violation Categories Reference"):
        for rule_name, rule_data in VIOLATION_RULES.items():
            severity = rule_data['severity']
            if severity == 'critical':
                st.error(f"🔴 **{rule_name.replace('_', ' ')}**")
            elif severity == 'high':
                st.warning(f"🟠 **{rule_name.replace('_', ' ')}**")
            else:
                st.info(f"🟡 **{rule_name.replace('_', ' ')}**")
            
            st.write(rule_data['description'])
            st.write(f"**Keywords:** {', '.join(rule_data['keywords'])}")
            st.divider()

if __name__ == "__main__":
    main()
