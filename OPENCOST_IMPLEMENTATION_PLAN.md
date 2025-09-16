# OpenCost Reporting Feature Implementation Plan

## Executive Summary

Implementation plan for adding OpenCost metadata export functionality to CODA.
OpenCost is a standardized XML format for exchanging publication cost data, enabling transparency in scholarly publishing costs.

**Architecture**: OpenCost Bounded Context following CODA's Domain-Driven Design patterns
**Scope**: Export CODA publication/contract data as OpenCost XML with web interface
**Status**: Ready for Phase 1 implementation

## Requirements Summary

### **Functional Requirements** ✅

- [ ] Export publication data in OpenCost XML format
- [ ] Export contract data in OpenCost XML format
- [ ] Support multi-institutional cost sharing for publications
- [ ] Handle multiple invoices per publication/contract
- [ ] Institution identifier management (ROR, ISNI, Ringold)
- [ ] Contract identifier management (ESAC, OAI, EZB, local)
- [ ] Contract invoice period grouping (group_id linking)
- [ ] Interactive web reports with navigation to current CODA pages
- [ ] Audit-compliant report snapshots

### **Technical Requirements** ✅

- [ ] Bounded context architecture (separate from other CODA domains)
- [ ] Domain models with business logic (cost sharing validation)
- [ ] Django models for persistence (following CODA patterns)
- [ ] Anti-corruption layer (CODA ↔ OpenCost transformation)
- [ ] Repository pattern for domain-Django mapping
- [ ] Bulk query optimization for large datasets
- [ ] Streaming XML generation for performance
- [ ] Caching strategy for frequently accessed data

### **OpenCost Schema Compliance** ✅

- [ ] Publication `external_costsplitting` boolean field
- [ ] Contract identifier primary/secondary types
- [ ] Institution identifier primary/secondary types
- [ ] Flexible date formats (YYYY, YYYY-MM, YYYY-MM-DD)
- [ ] Multiple invoice support (`maxOccurs="unbounded"`)
- [ ] Group ID linking mechanism for contract-publication relationships
- [ ] All required/optional fields per OpenCost XSD

## Goals

- Export CODA publication and contract data in OpenCost XML format using efficient bulk queries
- Create and save OpenCost reports for institutions with optimized data loading
- Support both individual publications and bulk exports with proper performance considerations
- Maintain data integrity and validation according to OpenCost schema
- Respect bounded context boundaries and avoid domain model coupling

## Architecture Overview

**OpenCost Bounded Context** following CODA's Domain-Driven Design:

- **Domain Layer** (`src/coda/domain/opencost/`): OpenCost schema models, business logic
- **Application Layer** (`src/coda/apps/opencost/`): Data aggregation, transformation services
- **Infrastructure Layer**: XML generation, web interface, API endpoints

**Key Principles:**

- **Bounded Context Independence**: Separate domain models from other CODA contexts
- **Anti-Corruption Layer**: Clean CODA ↔ OpenCost data transformation
- **Query Optimization**: Bulk operations for large institutional datasets
- **Audit Compliance**: Immutable report snapshots with navigation links

## Implementation Roadmap

### **Phase 1: Domain Service & Application Layer Development** ⭐ *Start Here*

**Objective**: Build application layer services that transform CODA data using existing OpenCost domain models
**Duration**: 1-2 sprints
**Status**: Ready to begin

#### **1.1 OpenCost Data Aggregation Services**

**File**: `src/coda/apps/opencost/data_aggregation.py`

- **Bulk Data Loading**: Efficient queries using `select_related`, `prefetch_related` for report generation
- **Publication Data Aggregation**: Single query to load publications with related invoices, contracts, authors
- **Contract Data Aggregation**: Optimized loading of contracts with invoice groups and cost data
- **Invoice Grouping**: Efficient grouping and aggregation of invoice data by contract periods

#### **1.2 OpenCost Domain Models (Bounded Context)**

**File**: `src/coda/domain/opencost/report_models.py` (New)

- **OpenCost-Specific Value Objects**: OpenCostPublicationCost, OpenCostContractCost, OpenCostInstitution
- **Report Aggregates**: OpenCostReport with publications, contracts, metadata
- **Domain Rules**: Cost calculation, date formatting, identifier validation within OpenCost context
- **No External Dependencies**: OpenCost domain models remain independent of other bounded contexts

#### **1.3 Transformation Services (Anti-Corruption Layer)**

**File**: `src/coda/apps/opencost/transformers.py`

- **Data Conversion**: Transform Django model data → OpenCost domain models
- **Bounded Context Translation**: Map CODA concepts to OpenCost equivalents without domain coupling
- **Batch Processing**: Process large datasets efficiently for report generation
- **Data Validation**: Ensure OpenCost schema compliance during transformation

#### **1.4 Optimized Query Strategies**

#### **1.4 Supporting Data Models**

#### **1.4 Optimized Query Strategies**

**File**: `src/coda/apps/opencost/queries.py`

- **Publication Report Query**: Single query with joins for publications + invoices + contracts + institutions
- **Contract Report Query**: Optimized loading of contract data with related invoice groups and payments
- **Bulk Processing**: Pagination and batching for large institutions with thousands of publications
- **Query Performance**: Use raw SQL or custom QuerySets for complex aggregations when needed

The bounded context will implement efficient data loading patterns following CODA's established query optimization approaches.

---

### **Phase 2: Bounded Context Services & Anti-Corruption Layer**

**Objective**: Build transformation services that respect bounded context boundaries
**Duration**: 2-3 sprints

#### **2.1 Anti-Corruption Layer**

**File**: `src/coda/apps/opencost/anti_corruption.py`

- **Context Translation**: Convert CODA models to OpenCost-specific structures without domain coupling
- **Data Mapping**: Transform CODA Publication → OpenCost Publication (not shared domain objects)
- **Invoice Transformer**: CODA Invoice → OpenCost invoice types
- **Institution Transformer**: CODA Institution → OpenCost InstitutionType

#### **2.2 Business Logic Services**

**File**: `src/coda/apps/opencost/domain_services.py`

- **Report Generation Orchestration**: Coordinate data collection and transformation
- **Validation Services**: Ensure OpenCost schema compliance using domain models
- **Data Consistency Checks**: Verify group_id linking and referential integrity

---

### **Phase 3: XML Generation & Infrastructure Layer**

**Objective**: Create XML serialization and web interface using transformed domain models
**Duration**: 2-3 sprints

#### **3.1 XML Generation Services**

**File**: `src/coda/apps/opencost/xml_generation.py`

- **OpenCost XML Serialization**: Convert OpenCost domain models to XML using Pydantic
- **Schema Validation**: Ensure generated XML complies with opencost.xsd
- **Multi-Entity Reports**: Handle publications + contracts in single XML document

#### **3.2 Web Interface & API**

**File**: `src/coda/apps/opencost/views.py`

- **Report Management UI**: Create, view, download OpenCost reports
- **Interactive Report Display**: Web-friendly presentation of OpenCost data
- **Download Endpoints**: XML file generation and delivery

#### **3.3 Report Storage & Metadata**

**Goal**: Store report metadata for audit compliance while leveraging domain models for business logic

- **Report Snapshots**: Immutable data for institutional reporting requirements
- **XML Content Storage**: Generated XML for consistent downloads
- **Regeneration Capability**: Re-run transformation using current domain logic

---

## **Test-Driven Development Strategy**

*Following CODA's TDD practices with clear Given/When/Then scenarios for all OpenCost functionality.*

### **Domain Model Tests - Cost Sharing Logic**

*Location: `tests/domain/test_invoice_cost_sharing.py`*

#### **Cost Share Creation and Validation**

**Valid Cost Sharing Arrangement Creation**

- **GIVEN**: A publication position with €1000 cost
- **WHEN**: Creating cost shares for 2 institutions (€600 + €400)
- **THEN**: Cost sharing arrangement validates successfully with complete split

**Invalid Cost Sharing Sum Validation**

- **GIVEN**: A publication position with €1000 cost
- **WHEN**: Creating cost shares that sum to €900 (incomplete)
- **THEN**: Validation fails indicating incomplete cost coverage

**Single Institution Payment Detection**

- **GIVEN**: A publication position paid by single institution
- **WHEN**: Checking external cost splitting status
- **THEN**: Returns False (no external cost splitting)

**Contract Position Cost Sharing Restriction**

- **GIVEN**: A contract position (not publication)
- **WHEN**: Attempting to add cost sharing
- **THEN**: Validation error raised (contracts don't support cost splitting per OpenCost)

### **Django Model Tests - Persistence and Constraints**

*Location: `tests/models/test_opencost_cost_sharing.py`*

#### **Database Constraint Testing**

**Cost Share Unique Constraint Enforcement**

- **GIVEN**: A publication position with existing cost share for institution
- **WHEN**: Creating duplicate cost share for same position+institution
- **THEN**: Database constraint prevents duplicate with IntegrityError

**Publication-Only Cost Share Constraint**

- **GIVEN**: A contract position (no publication)
- **WHEN**: Attempting to create cost share
- **THEN**: Database constraint prevents creation with IntegrityError

**Cost Sharing Domain Model Conversion**

- **GIVEN**: A publication position with cost shares in database
- **WHEN**: Converting to domain model via enhanced Position
- **THEN**: Returns proper PublicationCostSharingArrangement with all shares

### **Service Layer Tests - Data Transformation**

*Location: `tests/services/test_opencost_transformation.py`*

#### **CODA to OpenCost Transformation**

**Multi-Institution Publication Transformation**

- **GIVEN**: A CODA publication with multi-institutional cost sharing
- **WHEN**: Transforming to OpenCost format
- **THEN**: external_costsplitting=true and correct cost data structure

**Single Institution Publication Transformation**

- **GIVEN**: A CODA publication paid by single institution
- **WHEN**: Transforming to OpenCost format
- **THEN**: external_costsplitting=false

**Contract with Invoice Groups Transformation**

- **GIVEN**: A CODA contract with invoice groups and group_id
- **WHEN**: Transforming to OpenCost format
- **THEN**: Contract has correct invoice_group with group_id and all invoices

### **Integration Tests - End-to-End Workflows**

*Location: `tests/integration/test_opencost_report_generation.py`*

#### **Complete Report Generation**

**Complex Institution Report Generation**

- **GIVEN**: Institution with publications having cost sharing + contracts with groups
- **WHEN**: Generating complete OpenCost report
- **THEN**: XML validates against schema with correct cost splitting data

**Report XML Structure Validation**

- **GIVEN**: Generated OpenCost report with cost sharing data
- **WHEN**: Parsing XML structure
- **THEN**: Contains proper publication elements with external_costsplitting flags

### **Performance Tests - Bulk Operations**

*Location: `tests/performance/test_opencost_bulk_operations.py`*

#### **Large Dataset Performance**

**Bulk Cost Sharing Query Performance**

- **GIVEN**: 1000 publications with cost sharing data
- **WHEN**: Generating OpenCost report
- **THEN**: Completes within 30 seconds with <100 database queries

**Memory Usage Optimization**

- **GIVEN**: Large institution with thousands of publications
- **WHEN**: Processing cost sharing calculations
- **THEN**: Memory usage remains below 500MB throughout process

### **Schema Validation Tests**

*Location: `tests/validation/test_opencost_schema.py`*

#### **OpenCost XML Compliance**

**Cost Splitting XML Schema Validation**

- **GIVEN**: Generated OpenCost XML with cost splitting data
- **WHEN**: Validating against OpenCost XSD schema
- **THEN**: All elements validate without schema errors

**Required Field Presence Validation**

- **GIVEN**: OpenCost publication with external cost splitting
- **WHEN**: Checking required fields in XML
- **THEN**: All mandatory elements present (external_costsplitting, cost_data, etc.)

### **Test Execution Strategy**

- **Red-Green-Refactor**: Write failing test, make it pass, refactor
- **Test Categories**: Unit (fast), Integration (thorough), Performance (separate)
- **Coverage Targets**: Domain 100%, Models 95%, Services 90%
- **CI Integration**: All tests must pass before merge

---

## **Detailed Implementation Strategy**

### **Bounded Context Architecture**

#### **OpenCost Bounded Context (Independent)**

- **Location**: `src/coda/domain/opencost/`, `src/coda/apps/opencost/`
- **Components**: OpenCost-specific domain models, aggregation services, report generation
- **Isolation**: No direct references to Publication, Contract, or Invoice domain models
- **Communication**: Data transfer via application services, not shared domain objects

#### **Application Layer (Anti-Corruption)**

- **Location**: `src/coda/apps/opencost/`
- **Components**: Data aggregation, transformation services, optimized queries
- **Responsibility**: Convert CODA data → OpenCost data, bulk processing, persistence

#### **Infrastructure Layer (Performance-Optimized)**

- **Components**: Efficient XML serialization, bulk report generation, web interfaces
- **Responsibility**: High-performance data export, user interaction, file delivery

### **Key Implementation Patterns**

#### **Bounded Context Pattern**

The anti-corruption layer will convert CODA publication data to OpenCost-specific structures using efficient bulk queries and transformation services, maintaining complete independence between the bounded contexts.

#### **Repository Pattern Implementation**

The OpenCost bounded context will implement repository patterns for efficient data access and transformation, following CODA's established architectural patterns.

#### **Performance Optimization Strategy**

Report generation will use optimized bulk queries, batched transformations, and streaming XML serialization to handle large datasets efficiently while maintaining memory efficiency.

### **Performance Considerations**

#### **Query Optimization Strategies**

- **Bulk Loading**: Use `select_related` and `prefetch_related` to minimize database queries
- **Aggregation at Database Level**: Calculate totals and counts in SQL rather than Python
- **Pagination**: Process large datasets in chunks to avoid memory issues
- **Raw SQL**: Use custom SQL for complex aggregations when Django ORM is insufficient

#### **Memory Management**

- **Streaming XML Generation**: Generate XML in chunks for very large reports
- **Lazy Evaluation**: Use generators and iterators for large datasets
- **Garbage Collection**: Explicit cleanup for large data processing

#### **Caching Strategy**

- **Institution Data**: Cache institution identifiers and metadata
- **Report Metadata**: Cache report generation statistics and summaries
- **Template Data**: Cache frequently accessed configuration data

The bounded context will implement these optimization patterns using established CODA approaches.

### **Django Integration Layer**

The OpenCost bounded context will include minimal Django models for:

- Report metadata persistence
- OpenCost-specific identifiers (ROR, ISNI, ESAC IDs) using CODA's established Link patterns
- Anti-corruption layer between CODA and OpenCost formats

---

## **Architecture Alignment**

### **✅ Domain-Driven Design Approach**

**Implementation Strategy**:

- **Domain Layer**: Leverage existing OpenCost Pydantic models in `src/coda/domain/opencost/`
- **Application Layer**: Create services, repositories, minimal Django models in `src/coda/apps/opencost/`
- **Infrastructure Layer**: XML generation, web views, API endpoints

### **✅ Bounded Context Benefits**

1. **Phase 1**: Application layer services transforming CODA to OpenCost formats
2. **Phase 2**: Domain service orchestration and business logic coordination
3. **Phase 3**: Infrastructure layer for XML generation and web interface

### **✅ Key Advantages**

- **Separation of Concerns**: Business logic in domain, persistence in application layer
- **Leverage Existing Code**: OpenCost domain models already implement schema compliance
- **Maintainability**: Clear boundaries between domain rules and infrastructure concerns
- **Testability**: Domain logic can be tested independently of Django infrastructure

---

## **🎯 Complete Bounded Context Implementation Strategy - Ready to Execute!**

### **Implementation Notes**

The above transformation services will handle the complex mapping between CODA's domain model and OpenCost requirements, including:

- Publication-contract linking via `group_id` mechanism
- Multi-invoice support for both publications and contracts
- Institution identifier mapping (ROR, ISNI, etc.)
- Cost splitting data transformation
- Date format conversion (YYYY, YYYY-MM, YYYY-MM-DD)
- VAT handling according to OpenCost schema

---

## **🎯 Complete DDD Implementation Strategy - Ready to Execute!**

### **Export & Reporting Strategy - Finalized ✅**

- **Generation**: On-demand report creation (primarily yearly, flexible timing)
- **Storage**: Database persistence with snapshot approach for audit trails
- **Web Interface**: HTML viewing with clickable navigation to current CODA pages
- **Download**: XML file download for external system integration
- **Management**: List, view, regenerate reports through web interface

### **All Requirements Clarified ✅**

1. ✅ **Institution Identifiers**: Starting fresh (no existing data migration)
2. ✅ **User Permissions**: Single-institution deployment (no cross-institutional concerns)
3. ✅ **Contract Invoice Groups**: OpenCost billing period grouping requirements understood
4. ✅ **Export Strategy**: On-demand generation with web viewing and database storage
5. ✅ **Data Consistency**: Snapshot approach for audit compliance and regulatory requirements
6. ✅ **Architecture**: Bounded context with anti-corruption layer and query optimization
7. ✅ **Performance**: Bulk processing strategies for large institutions and datasets

### **Architectural Principles Established ✅**

#### **Bounded Context Independence**

- OpenCost has its own domain models, separate from CODA Publication/Contract/Invoice contexts
- No shared domain objects between contexts - data transfer via application services only
- OpenCost business rules and validation contained within its bounded context

#### **Query Performance Optimization**

- Bulk data loading using `select_related` and `prefetch_related` patterns
- Database-level aggregation to minimize memory usage and processing time
- Streaming XML generation for very large reports
- Pagination and batching for institutions with thousands of publications

#### **Anti-Corruption Layer Pattern**

- Application services transform CODA data → OpenCost-specific structures
- No direct references to other domain models from OpenCost context
- Clean mapping layer that can evolve independently

### **Technical Foundation Ready ✅**

- **Bounded Context**: Independent OpenCost domain with optimized models for reporting performance
- **Anti-Corruption Layer**: Clean separation between CODA and OpenCost contexts via application services
- **Query Optimization**: Bulk data loading strategies to handle large institutions efficiently
- **Domain Independence**: OpenCost models don't share dependencies with other CODA contexts
- **OpenCost Compliance**: Schema requirements fully analyzed with performance-optimized implementation
- **Memory Management**: Streaming and batching strategies for large report generation
- **Audit Compliance**: Immutable report snapshots with efficient data aggregation

**Status**: 📋 Planning phase complete - Ready for Phase 1.1 implementation using bounded context architecture
**Next Step**: Begin Phase 1.1 - Optimized Data Aggregation Services (independent OpenCost context)
**Architecture**: Bounded Context with anti-corruption layer + performance-optimized bulk processing
**Last Updated**: September 5, 2025
The bounded context will implement audit fields and data integrity constraints using established CODA patterns.

**Benefits of Snapshot-Based Report Storage**:

- ✅ **Immutable Reports**: Report data never changes after generation (audit compliance)
- ✅ **Interactive Navigation**: Click publications/contracts → current CODA detail pages
- ✅ **Data Change Detection**: Visual indicators when current data differs from report
- ✅ **Historical Accuracy**: Reports reflect data as it existed at generation time
- ✅ **Audit Trail**: Complete lineage of what data was included and when
- ✅ **Performance**: Pre-computed totals for fast web display
- ✅ **Regulatory Compliance**: Meets financial reporting standards for immutability

**User Experience Pattern**:

```html
<!-- Report shows snapshot data with change indicators -->
<div class="publication-row">
  <h4>{{ report_pub.publication_title }}</h4>  <!-- Frozen snapshot -->
  <span class="cost">{{ report_pub.cost_total }} {{ report_pub.currency }}</span>
  {% if report_pub.has_data_changed %}
    <span class="badge warning">Data Updated Since Report</span>
  {% endif %}
  <a href="{{ report_pub.get_current_publication_url }}">View Current Details →</a>
</div>
```

#### **3.3 Data Consistency Strategy - Why Snapshot Approach?**

**Problem**: Publication/invoice data can change after report generation

**Alternative Approaches Considered**:

1. **Live Links Only** ❌
   - Reports would change when underlying data changes
   - Violates audit requirements for institutional reporting
   - Year-over-year comparisons become impossible

2. **Complete Data Duplication** ❌
   - Massive storage overhead
   - Complex synchronization logic
   - Difficult to maintain

3. **Snapshot Key Fields** ✅ **CHOSEN APPROACH**
   - Store critical display fields (title, DOI, costs) at report time
   - Maintain links for navigation to current data
   - Detect and indicate when data has changed
   - Balances auditability with usability

**Real-World Parallel**: Similar to how financial systems handle month-end closing - the report is locked, but you can still drill down to see current account status.

#### **3.4 Decision Rationale Documentation** 📋

**Context**: During implementation planning (September 2025), we faced a critical design decision about how to handle data consistency in OpenCost reports when underlying publication/invoice data changes after report generation.

**Key Question**: Should reports reflect current data (live) or snapshot data (frozen)?

**Stakeholder Considerations Identified**:

1. **Institutional Reporting Needs**
   - Annual reports to funding agencies (requires stable data)
   - Multi-year trend analysis (needs historical consistency)
   - Audit compliance (regulatory requirement for immutable records)

2. **User Experience Requirements**
   - Report viewing months after generation
   - Navigation to detailed CODA pages
   - Understanding when data has changed since report creation

3. **Technical Constraints**
   - OpenCost XML must be downloadable and stable
   - Web interface should be interactive and performant
   - System should handle publication deletions gracefully

**Analysis of Alternative Approaches**:

| Approach | Storage | Audit Compliance | User Experience | Technical Complexity |
|----------|---------|------------------|-----------------|---------------------|
| **Live Links Only** | Minimal | ❌ Reports change | ❌ Confusing | Low |
| **Full Data Duplication** | Very High | ✅ Complete | ✅ Self-contained | Very High |
| **Key Field Snapshots** | Medium | ✅ Stable core data | ✅ Best of both | Medium |

**Decision Made**: **Key Field Snapshots** (Hybrid Approach)

**Justification**:

- **Regulatory**: Meets audit requirements for institutional reporting
- **Practical**: Balances storage efficiency with data stability
- **Usable**: Provides both stable report data AND current detail access
- **Industry Standard**: Follows financial systems best practices (QuickBooks, SAP)

**Implementation Compromise**: Store essential display fields (title, DOI, costs) as snapshots while maintaining foreign key relationships for navigation to current data.

**Future Consideration**: If storage becomes an issue, we can implement data archiving strategies, but the core snapshot approach should remain for audit compliance.

**Date of Decision**: September 5, 2025
**Decision Participants**: Technical team, understanding institutional reporting requirements

---

### **Phase 4: User Interface & API**

**Objective**: Build Django views, templates, and web interfaces for OpenCost reporting
**Duration**: 2-3 sprints

#### **4.1 Web Interface Features**

- **Report Dashboard**: List of generated OpenCost reports with summaries and statistics
- **Report Generation Form**: User interface to create new reports with date ranges and filters
- **Interactive Report Viewer**:
  - Tabbed interface (Publications, Contracts, Summary)
  - Clickable publications → publication detail pages
  - Clickable contracts → contract detail pages
  - Clickable invoices → invoice detail pages
  - Cost breakdown tables with filtering and sorting
- **Download Interface**: XML file download with proper content-type headers
- **Report Management**: Edit report metadata, regenerate reports when data changes

#### **4.2 User Experience Flow**

1. **Generate Report**: User selects date range and clicks "Generate OpenCost Report"
2. **Processing**: System creates XML, stores relational data, shows progress
3. **Interactive Report View**:
   - Summary tab with statistics and totals
   - Publications tab with clickable links to publication details
   - Contracts tab with clickable links to contract details
   - Cost breakdown with drill-down capabilities
4. **Navigation**: Click any publication/contract/invoice to view detailed CODA pages
5. **Download**: User can download XML file for external systems
6. **Management**: List of historical reports with regeneration options

#### **4.3 Template Structure**

```html
<!-- OpenCost Report Viewer Template -->
<div class="opencost-report">
  <header>
    <h1>{{ report.title }}</h1>
    <p>Period: {{ report.period_start }} - {{ report.period_end }}</p>
    <a href="{% url 'opencost:download' report.pk %}" class="btn">Download XML</a>
  </header>

  <nav class="report-tabs">
    <button data-tab="summary">Summary</button>
    <button data-tab="publications">Publications ({{ report.publications.count }})</button>
    <button data-tab="contracts">Contracts ({{ report.contracts.count }})</button>
  </nav>

  <div id="publications-tab">
    {% for report_pub in report.publications.all %}
      <div class="publication-row">
        <a href="{% url 'publications:detail' report_pub.publication.pk %}">
          {{ report_pub.publication.title }}
        </a>
        <span class="cost">{{ report_pub.cost_total }} {{ report_pub.currency }}</span>
        {% if report_pub.has_cost_splitting %}<span class="badge">Cost Shared</span>{% endif %}
      </div>
    {% endfor %}
  </div>
</div>
```

---

### **Phase 5: Advanced Features**

**Objective**: Data validation, quality checks, and advanced reporting features
**Duration**: 1-2 sprints

#### **5.1 Data Quality & Validation**

- **OpenCost Readiness Checker**: Dashboard showing data completeness for OpenCost export
- **Missing Data Reports**: Identify publications/contracts lacking required identifiers
- **Validation Rules**: Pre-export checks for OpenCost schema compliance
- **Data Quality Metrics**: Statistics on identifier coverage, cost completeness

#### **5.2 Advanced Features**

- **Report Templates**: Predefined report configurations for common use cases
- **Bulk Operations**: Mass assignment of identifiers, cost sharing arrangements
- **Export Scheduling**: Optional automated report generation (future enhancement)

---

### **Phase 6: Testing & Documentation**

**Objective**: Comprehensive testing and user documentation
**Duration**: 1 sprint

## **Phase 1 Detailed Implementation** 🚀

### **1.1 Institution Identifiers (Future-Proof Design)**

**Task**: Create flexible institution identifier system
**Files**: New models extending institution system
**Pattern**: Follow CODA's Link pattern for maximum extensibility

#### **Recommended Approach: Institution Identifier Support**

For OpenCost compliance, institutions will need identifier support (ROR, ISNI, Ringold). This will be implemented following CODA's existing Link pattern for flexibility.

**Benefits**:

- ✅ **Zero schema changes** for new OpenCost identifier types
- ✅ **Simple querying**: Following established CODA patterns
- ✅ **Type safety**: Consistent with CODA architecture
- ✅ **Performance**: Optimized for bulk report generation

### **Contract Identifier Support**

Similarly, contracts will need identifier support for OpenCost (ESAC, OAI, EZB, local) following the same flexible pattern.

**Task**: Create flexible contract identifier system following CODA patterns
**Files**: Contract identifier support
**Pattern**: Mirror Institution identifier approach for consistency

### **Cost Sharing Support for Publications**

**Critical Requirement**: Support publication cost sharing between institutions as required by OpenCost schema.

**Invoice Domain Integration**: Cost sharing should be implemented as part of the invoice domain model since it represents real-world payment arrangements. When a publication position is paid by multiple institutions, this needs to be captured at the position level.

**OpenCost Mapping**:

- **`external_costsplitting`**: Boolean field derived from whether a publication position has multiple institutional cost shares
- **Business Logic**: Only publications support cost splitting (contracts do not in OpenCost schema)
- **Data Source**: Publication position cost shares within invoice positions

**Domain Model Requirements**:

1. **Publication Position Cost Shares**: Track which institutions pay what portion of a publication position
2. **Cost Share Validation**: Ensure shares sum to the total position cost
3. **External Cost Splitting Detection**: Derive OpenCost `external_costsplitting` flag from presence of multiple institutional shares
4. **Integration Point**: Anti-corruption layer transforms invoice cost sharing data to OpenCost format

**Key Insight**: This belongs in the invoice domain because it represents actual payment arrangements captured when invoices are processed, not just OpenCost export metadata.

### **Implementation Strategy Summary**

The bounded context approach will handle:

- **Institution Identifiers**: Support for ROR, ISNI, Ringold IDs using CODA's flexible patterns
- **Contract Identifiers**: ESAC, OAI, EZB, local identifiers with the same flexibility
- **Cost Sharing**: Publication-level cost sharing between institutions as required by OpenCost
- **Performance Optimization**: Bulk data loading and efficient query patterns for large institutions
- **Domain Independence**: OpenCost models isolated from other CODA contexts

### **Invoice Domain Model Enhancements**

**Critical**: Publication cost sharing must be integrated into the invoice domain model, not just the OpenCost bounded context.

**Required Changes to `/app/src/coda/domain/invoice.py`**:

1. **Cost Share Domain Models**:
   - `InstitutionCostShare` - individual institution's portion of a position cost
   - `PublicationCostSharingArrangement` - collection of institutional shares
   - Enhanced `Position` class with optional cost sharing for publication positions

2. **Business Logic**:
   - Validation that cost shares sum to position total
   - `has_external_cost_splitting()` method for OpenCost export
   - Publication-only constraint (contracts don't support cost splitting per OpenCost)

3. **Integration Points**:
   - Django model extensions for cost share persistence
   - Repository pattern updates for cost share CRUD operations
   - Anti-corruption layer mapping to OpenCost schema

**Why Invoice Domain**: Cost sharing represents real payment arrangements when invoices are processed, making it core invoice domain logic rather than export-specific metadata.

### **Django Models for Domain Persistence**

**Architecture**: Domain models contain business logic, Django models provide persistence mapping following CODA's established patterns.

**Database Design Principles**:

- **CODA Pattern Compliance**: Follow existing `LinkType`/`Link` pattern for identifiers
- **Referential Integrity**: Proper foreign key constraints and cascading behavior
- **Performance Optimization**: Strategic indexes for OpenCost bulk queries
- **Data Validation**: Database-level constraints for business rules
- **Audit Compliance**: Immutable snapshots with change tracking

#### **Cost Sharing Django Models**

```python
# src/coda/apps/invoices/models.py - Extensions

class PublicationPositionCostShare(models.Model):
    """Individual institution's share of a publication position's cost"""
    position = models.ForeignKey(
        'Position',
        on_delete=models.CASCADE,
        related_name="publication_cost_shares",
        limit_choices_to={'publication__isnull': False}  # Only publication positions
    )
    institution = models.ForeignKey(
        'institutions.Institution',
        on_delete=models.CASCADE
    )

    # Cost details (matching OpenCost schema requirements)
    amount = models.DecimalField(max_digits=20, decimal_places=4)
    currency = models.CharField(max_length=3)  # ISO 4217 format
    cost_type = models.CharField(max_length=50)  # Must match OpenCost PublicationCostType

    class Meta:
        unique_together = ('position', 'institution')
        constraints = [
            # Ensure only publication positions can have cost shares
            models.CheckConstraint(
                check=models.Q(position__publication__isnull=False),
                name='cost_sharing_publication_only'
            ),
        ]

    def __str__(self):
        return f"{self.institution.name}: {self.amount} {self.currency}"


# Enhanced Position model (existing model extension)
class Position(models.Model):
    # ... existing fields unchanged ...

    def get_publication_cost_sharing(self):
        """Convert Django cost shares to domain model (publications only)"""
        if not self.publication or not self.publication_cost_shares.exists():
            return None

        # Return cost sharing arrangement for domain layer
        shares = list(self.publication_cost_shares.all())
        return shares  # Will be converted to domain objects in application layer

    def has_external_cost_splitting(self) -> bool | None:
        """OpenCost external_costsplitting derived from cost_sharing"""
        if not self.publication:
            return None  # Not applicable to contract positions

        cost_share_count = self.publication_cost_shares.count()
        if cost_share_count == 0:
            return None  # Unknown - no cost sharing data

        return cost_share_count > 1
```

#### **OpenCost Report Django Models**

```python
# src/coda/apps/opencost/models.py - New app

class OpenCostReport(models.Model):
    """OpenCost report metadata and persistence"""
    institution = models.ForeignKey('institutions.Institution', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    period_start = models.DateField()
    period_end = models.DateField()
    generated_at = models.DateTimeField(auto_now_add=True)
    xml_content = models.TextField()  # Complete OpenCost XML
    data_snapshot_date = models.DateTimeField()

    class Meta:
        ordering = ['-generated_at']

    def __str__(self):
        return f"{self.title} ({self.institution.name}) - {self.generated_at.date()}"


class OpenCostReportPublication(models.Model):
    """Snapshot of publication data in report for audit trail"""
    report = models.ForeignKey(OpenCostReport, on_delete=models.CASCADE, related_name="publications")
    publication = models.ForeignKey('publications.Publication', on_delete=models.CASCADE)

    # Publication snapshot data (fields required for OpenCost XML generation)
    title = models.CharField(max_length=500)
    doi = models.CharField(max_length=255, blank=True)
    publication_type = models.CharField(max_length=100)

    # OpenCost-specific fields
    has_external_cost_splitting = models.BooleanField(null=True)

    # Contract linkage (if applicable - from OpenCost part_of_contract)
    part_of_contract = models.ForeignKey('contracts.Contract', on_delete=models.CASCADE, null=True, blank=True)
    contract_group_id = models.CharField(max_length=100, blank=True)

    # Institution data for OpenCost
    institution_name = models.CharField(max_length=255)

    # Audit field
    data_snapshot_date = models.DateTimeField()

    class Meta:
        unique_together = ('report', 'publication')

    def get_current_publication_url(self):
        """Link to current publication"""
        from django.urls import reverse
        return reverse('publications:detail', kwargs={'pk': self.publication_id})


class OpenCostReportContract(models.Model):
    """Snapshot of contract data in report for audit trail"""
    report = models.ForeignKey(OpenCostReport, on_delete=models.CASCADE, related_name="contracts")
    contract = models.ForeignKey('contracts.Contract', on_delete=models.CASCADE)

    # Contract snapshot data (fields required for OpenCost XML)
    contract_name = models.CharField(max_length=255)

    # Institution data for OpenCost
    institution_name = models.CharField(max_length=255)

    # Audit field
    data_snapshot_date = models.DateTimeField()

    class Meta:
        unique_together = ('report', 'contract')

    def get_current_contract_url(self):
        """Link to current contract"""
        from django.urls import reverse
        return reverse('contracts:detail', kwargs={'pk': self.contract_id})


class OpenCostReportInvoice(models.Model):
    """Snapshot of invoice data in report for audit trail"""
    report = models.ForeignKey(OpenCostReport, on_delete=models.CASCADE, related_name="invoices")
    publication_report = models.ForeignKey(
        OpenCostReportPublication,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="invoices"
    )
    contract_report = models.ForeignKey(
        OpenCostReportContract,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="invoices"
    )

    # Invoice snapshot data (fields required for OpenCost XML)
    invoice = models.ForeignKey('invoices.Invoice', on_delete=models.CASCADE)
    invoice_number = models.CharField(max_length=255, blank=True)
    creditor = models.CharField(max_length=255, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    paid_date = models.DateField(null=True, blank=True)

    # Contract-specific fields (for OpenCost contract invoice groups)
    invoice_group_id = models.CharField(max_length=100, blank=True)

    # Audit field
    data_snapshot_date = models.DateTimeField()

    class Meta:
        unique_together = ('report', 'invoice')
        constraints = [
            # Invoice must belong to either publication or contract (XOR)
            models.CheckConstraint(
                check=(
                    models.Q(publication_report__isnull=False, contract_report__isnull=True) |
                    models.Q(publication_report__isnull=True, contract_report__isnull=False)
                ),
                name='invoice_belongs_to_publication_or_contract'
            )
        ]

    def get_current_invoice_url(self):
        """Link to current invoice"""
        from django.urls import reverse
        return reverse('invoices:detail', kwargs={'pk': self.invoice_id})
```

    class Meta:
        unique_together = ('report', 'invoice')
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(publication_report__isnull=False, contract_report__isnull=True) |
                    models.Q(publication_report__isnull=True, contract_report__isnull=False)
                ),
                name='invoice_belongs_to_publication_or_contract'
            )
        ]

    def get_current_invoice_url(self):
        """Link to current invoice (may have changed since report)"""
        return reverse('invoices:detail', kwargs={'pk': self.invoice_id})

```

#### **Contract Invoice Groups Django Models**

```python
# src/coda/apps/contracts/models.py - Extensions

class ContractInvoiceGroup(models.Model):
    """Groups contract invoices by period for OpenCost reporting"""
    contract = models.ForeignKey(
        'Contract',
        on_delete=models.CASCADE,
        related_name="invoice_groups"
    )
    group_id = models.CharField(max_length=100)
    period_start = models.DateField()
    period_end = models.DateField()

    class Meta:
        unique_together = ('contract', 'group_id')
        constraints = [
            models.CheckConstraint(
                check=models.Q(period_end__gte=models.F('period_start')),
                name='valid_invoice_period_range'
            )
        ]

    def __str__(self):
        return f"{self.contract.name} - {self.group_id} ({self.period_start} to {self.period_end})"


class InvoiceGroupMembership(models.Model):
    """Links invoices to contract invoice groups"""
    invoice = models.ForeignKey(
        'invoices.Invoice',
        on_delete=models.CASCADE,
        related_name="group_memberships"
    )
    group = models.ForeignKey(
        ContractInvoiceGroup,
        on_delete=models.CASCADE,
        related_name="invoice_memberships"
    )

    class Meta:
        unique_together = ('invoice', 'group')

    def __str__(self):
        return f"Invoice {self.invoice.number} in group {self.group.group_id}"


# Enhanced Contract model (existing model extension)
class Contract(models.Model):
    # ... existing fields unchanged ...

    def get_opencost_group_for_publication(self, publication, invoice_date=None):
        """Find the appropriate invoice group for linking a publication to this contract"""
        if not invoice_date:
            # Use publication date or current date as fallback
            invoice_date = getattr(publication, 'publication_date', timezone.now().date())

        # Find group that covers the invoice date
        matching_groups = self.invoice_groups.filter(
            period_start__lte=invoice_date,
            period_end__gte=invoice_date
        )

        return matching_groups.first()  # Return most recent if multiple matches

    def create_default_invoice_groups(self, year=None):
        """Create quarterly invoice groups for a contract year"""
        if not year:
            year = timezone.now().year

        quarters = [
            (1, 1, 3, 31),   # Q1: Jan-Mar
            (2, 4, 6, 30),   # Q2: Apr-Jun
            (3, 7, 9, 30),   # Q3: Jul-Sep
            (4, 10, 12, 31), # Q4: Oct-Dec
        ]

        groups = []
        for quarter, start_month, end_month, end_day in quarters:
            group_id = f"{year}-Q{quarter}"
            group, created = ContractInvoiceGroup.objects.get_or_create(
                contract=self,
                group_id=group_id,
                defaults={
                    'period_start': date(year, start_month, 1),
                    'period_end': date(year, end_month, end_day),
                    'description': f"{self.name} - {year} Quarter {quarter}"
                }
            )
            groups.append(group)

        return groups
```

#### **Identifier Django Models**

**Following CODA's Link Pattern**: These models extend the established `LinkType`/`Link` pattern for maximum flexibility and consistency.

```python
# src/coda/apps/institutions/models.py - Extensions

class InstitutionIdentifierType(models.Model):
    """Types of institution identifiers following CODA Link pattern"""
    name = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.display_name or self.name


class InstitutionIdentifier(models.Model):
    """Institution identifiers following CODA Link pattern"""
    institution = models.ForeignKey(
        'Institution',
        on_delete=models.CASCADE,
        related_name="identifiers"
    )
    type = models.ForeignKey(InstitutionIdentifierType, on_delete=models.CASCADE)
    value = models.CharField(max_length=255)

    class Meta:
        unique_together = ('institution', 'type', 'value')

    def __str__(self):
        return f"{self.type.name}: {self.value}"


# Enhanced Institution model (existing model extension)
class Institution(models.Model):
    # ... existing fields unchanged ...

    def get_primary_identifier(self, identifier_type=None):
        """Get identifier for OpenCost export"""
        if identifier_type:
            return self.identifiers.filter(type__name=identifier_type).first()
        return self.identifiers.first()

    def get_ror_id(self):
        """Get ROR identifier for OpenCost"""
        return self.get_primary_identifier('ror')

    def get_isni_id(self):
        """Get ISNI identifier for OpenCost"""
        return self.get_primary_identifier('isni')



```

### **Database Migration Strategy**

**Approach**: Incremental migrations with backward compatibility and zero-downtime deployment.

#### **Migration Phases**

**Phase 1: Core Infrastructure**

```python
# Migration 0001_opencost_base_models.py
# - Create OpenCostReport, OpenCostReportPublication, OpenCostReportContract
# - Create OpenCostReportInvoice with proper constraints
# - Add indexes for performance

# Migration 0002_identifier_types.py
# - Create InstitutionIdentifierType, ContractIdentifierType
# - Create InstitutionIdentifier, ContractIdentifier
# - Add CODA Link pattern compliance

# Migration 0003_cost_sharing.py
# - Create PublicationPositionCostShare model
# - Add constraints for publication-only cost sharing
# - Add methods to existing Position model

# Migration 0004_contract_invoice_groups.py
# - Create ContractInvoiceGroup, InvoiceGroupMembership
# - Add relationships to existing Contract model
# - Add helper methods for group management
```

**Phase 2: Data Initialization**

```python
# Migration 0005_seed_identifier_types.py - Data migration
def populate_identifier_types(apps, schema_editor):
    # Institution identifier types
    InstitutionIdentifierType = apps.get_model('institutions', 'InstitutionIdentifierType')
    institution_types = [
        {'name': 'ror', 'display_name': 'ROR ID', 'is_primary': True,
         'url_pattern': 'https://ror.org/{value}',
         'validation_regex': r'^https://ror\.org/[0-9a-z]+$'},
        {'name': 'isni', 'display_name': 'ISNI', 'is_primary': False,
         'url_pattern': 'https://isni.org/isni/{value}',
         'validation_regex': r'^[0-9]{4} [0-9]{4} [0-9]{4} [0-9]{3}[0-9X]$'},
        {'name': 'ringold', 'display_name': 'Ringgold ID', 'is_primary': False},
    ]

    for type_data in institution_types:
        InstitutionIdentifierType.objects.get_or_create(
            name=type_data['name'],
            defaults=type_data
        )

    # Contract identifier types
    ContractIdentifierType = apps.get_model('contracts', 'ContractIdentifierType')
    contract_types = [
        {'name': 'ESAC', 'display_name': 'ESAC Registry ID', 'is_primary': True,
         'url_pattern': 'https://esac-initiative.org/about/transformative-agreements/agreement-registry/agreement/{value}'},
        {'name': 'OAI', 'display_name': 'OAI Identifier', 'is_primary': False},
        {'name': 'EZB', 'display_name': 'EZB ID', 'is_primary': False},
        {'name': 'local', 'display_name': 'Local Identifier', 'is_primary': False},
    ]

    for type_data in contract_types:
        ContractIdentifierType.objects.get_or_create(
            name=type_data['name'],
            defaults=type_data
        )

# Migration 0006_populate_cost_types.py - Data migration
def populate_cost_types(apps, schema_editor):
    # Ensure PublicationPositionCostShare.cost_type choices match OpenCost schema
    # This might involve updating existing Position records to use OpenCost-compliant cost types
    pass
```

**Phase 3: Performance Optimization**

```python
# Migration 0007_performance_indexes.py
# - Add composite indexes for OpenCost bulk queries
# - Add partial indexes for verified identifiers only
# - Add indexes for report generation performance

CREATE INDEX CONCURRENTLY institutions_identifier_opencost_lookup
ON institutions_institutionidentifier (institution_id, type_id)
WHERE verified = true;

CREATE INDEX CONCURRENTLY contracts_identifier_opencost_lookup
ON contracts_contractidentifier (contract_id, type_id)
WHERE verified = true;

CREATE INDEX CONCURRENTLY positions_cost_sharing_opencost
ON invoices_publicationpositioncostshare (position_id, institution_id);

CREATE INDEX CONCURRENTLY invoice_groups_period_lookup
ON contracts_contractinvoicegroup (contract_id, period_start, period_end);
```

#### **Data Migration Considerations**

**Existing Data Handling**:

- **Publications without identifiers**: Valid - will use bibliographic_information fallback
- **Institutions without ROR/ISNI**: Valid - will use institution name in OpenCost
- **Contracts without ESAC ID**: Requires manual data entry or local identifier assignment
- **Positions without cost sharing**: Valid - represents single institution payment

**Backward Compatibility**:

- All new models are additive - no changes to existing model fields
- Existing Position model gains new methods but retains all current functionality
- OpenCost functionality is optional - doesn't affect existing workflows

**Performance During Migration**:

- Use `CONCURRENTLY` for index creation to avoid table locks
- Batch data processing for large tables
- Run migrations during low-traffic periods

#### **Rollback Strategy**

```python
# Each migration includes proper reverse operations
def reverse_migration_0003(apps, schema_editor):
    # Drop cost sharing models cleanly
    schema_editor.delete_model(apps.get_model('invoices', 'PublicationPositionCostShare'))

def reverse_migration_0004(apps, schema_editor):
    # Drop invoice group models
    schema_editor.delete_model(apps.get_model('contracts', 'InvoiceGroupMembership'))
    schema_editor.delete_model(apps.get_model('contracts', 'ContractInvoiceGroup'))
```

#### **Validation & Testing Strategy**

**Pre-Migration Validation**:

```python
# management/commands/validate_opencost_migration.py
class Command(BaseCommand):
    def handle(self, *args, **options):
        # Check for data consistency before migration
        # Validate existing position currencies match cost share requirements
        # Ensure no orphaned records that would violate new constraints
        # Report on institutions/contracts lacking required identifiers
```

**Post-Migration Verification**:

```python
# tests/migrations/test_opencost_migrations.py
class OpenCostMigrationTests(TransactionTestCase):
    def test_identifier_types_populated(self):
        # Verify all required identifier types exist

    def test_constraint_enforcement(self):
        # Verify database constraints work correctly

    def test_performance_indexes(self):
        # Verify indexes improve query performance
```

### **Domain-Django Mapping Strategy**

**Pattern**: Domain models contain business logic, Django models provide persistence with conversion methods:

1. **Domain → Django**: `from_domain_object()` class methods on Django models
2. **Django → Domain**: `to_domain_object()` instance methods on Django models
3. **Repository Pattern**: Handles conversion in repository layer
4. **Business Logic**: All validation and calculations in domain models
5. **Persistence**: Django models focus on data integrity and relationships

**Conversion Examples**:

```python
# Django to Domain conversion
class Position(models.Model):
    def to_domain_position(self):
        """Convert Django Position to domain Position with cost sharing"""
        cost_sharing = self.get_publication_cost_sharing()
        return DomainPosition(
            id=PositionId(self.id),
            amount=Money(self.cost_amount, Currency[self.cost_currency]),
            cost_type=CostType(self.cost_type),
            cost_sharing=cost_sharing,
            # ... other fields
        )

# Domain to Django conversion
class PublicationPositionCostShare(models.Model):
    @classmethod
    def from_domain_cost_sharing(cls, position, arrangement):
        """Create cost shares from domain model"""
        shares = []
        for share in arrangement.shares:
            django_share = cls(
                position=position,
                institution_id=share.institution_id,
                amount=share.amount.amount,
                currency=share.amount.currency.value,
                cost_type=share.cost_type.value,
                percentage=share.percentage
            )
            shares.append(django_share)
        return shares
```

### **Implementation Approach**

The OpenCost bounded context will implement the necessary domain models and query patterns while maintaining independence from other CODA contexts. Cost sharing capabilities will be handled through the domain model patterns established in CODA.

### **Database Performance Optimization**

**Query Optimization for OpenCost Reports**:

```python
# Optimized queries for bulk report generation
class OpenCostQueryOptimizer:
    @staticmethod
    def get_institution_publications_bulk(institution, period_start, period_end):
        """Single query to load all publication data for OpenCost report"""
        return Publication.objects.filter(
            positions__invoice__creditor__institution=institution,
            positions__invoice__date__range=[period_start, period_end]
        ).select_related(
            'journal',
            'journal__publisher'
        ).prefetch_related(
            'links',
            'positions__invoice',
            'positions__publication_cost_shares__institution',
            'attached_contracts__contract__identifiers__type'
        ).distinct()

    @staticmethod
    def get_institution_contracts_bulk(institution, period_start, period_end):
        """Single query to load all contract data for OpenCost report"""
        return Contract.objects.filter(
            positions__invoice__creditor__institution=institution,
            positions__invoice__date__range=[period_start, period_end]
        ).select_related().prefetch_related(
            'identifiers__type',
            'invoice_groups__invoice_memberships__invoice',
            'positions__invoice'
        ).distinct()
```

### **Next Steps**

1. **Database Setup**: Run migrations in development environment
2. **Data Seeding**: Populate identifier types and test data
3. **Performance Testing**: Validate query performance with realistic data volumes
4. **Integration Testing**: Ensure CODA workflows remain unaffected
4. **XML Generation**: Create streaming XML output following OpenCost schema
5. **Integration Testing**: Validate with sample data and performance testing

### **Contract Invoice Groups**

**Task**: Create model for OpenCost contract invoice grouping concept

**OpenCost Group ID Linking Mechanism:**
The `group_id` field is crucial for linking publications to specific contract invoice periods in OpenCost XML output:

1. **Contract Side**: `contract//cost_data//invoice_group//group_id`
2. **Publication Side**: `publication//cost_data//part_of_contract//group_id`
3. **Matching Rule**: Values must be identical to establish the link
4. **Use Case**: Enables publications to reference specific invoice periods within transformative agreements

The bounded context will implement this linking through appropriate domain models.

### **User Interface Considerations**

The bounded context approach will handle cost sharing UI through standard CODA patterns, maintaining consistency with existing invoice management interfaces.

**Benefits of the Publication-Focused Approach**:

- ✅ **OpenCost Compliant**: Aligns exactly with OpenCost schema requirements
- ✅ **Domain Accurate**: Reflects the actual business logic of cost splitting
- ✅ **Simplified Implementation**: Focused scope reduces complexity
- ✅ **Clear Semantics**: Cost sharing applies to publication payments as expected
- ✅ **Data Integrity**: Domain constraints ensure proper validation

### **Contract Invoice Groups**

**Task**: Create model for OpenCost contract invoice grouping concept

**OpenCost Group ID Linking Mechanism:**
The `group_id` field is crucial for linking publications to specific contract invoice periods in OpenCost XML output:

1. **Contract Side**: `contract//cost_data//invoice_group//group_id`
2. **Publication Side**: `publication//cost_data//part_of_contract//group_id`
3. **Matching Rule**: Values must be identical to establish the link
4. **Use Case**: Enables publications to reference specific invoice periods within transformative agreements

The bounded context will implement this linking through appropriate domain models.
**Example Group ID Linking Scenario:**

A contract might have invoice groups for specific periods (e.g., quarterly billing), and publications need to reference the appropriate group based on their payment timing. The OpenCost bounded context will implement this through domain models that track:

- Contract invoice periods and their unique group identifiers
- Publication-to-contract associations with the relevant group reference
- Proper validation to ensure group IDs exist and match

This enables the XML output to correctly link publications to specific contract billing periods.

# <part_of_contract>

# <group_id>deal-2024-q1</group_id>  <!-- From OpenCostReportPublication -->

**Implementation Approach**:

The bounded context will implement flexible identifier management following CODA's established Link pattern, supporting dynamic identifier types without schema constraints.

**Benefits**:

- ✅ **Zero schema changes** for new OpenCost identifier types
- ✅ **Admin interface** can manage identifier types
- ✅ **Database seeding** for current OpenCost types (ESAC, OAI, EZB, local)
- ✅ **Future OpenCost versions** supported automatically
- ✅ **Custom institutional identifiers** supported
- ✅ **Type safety** in domain layer with fallback patterns

**Domain Layer Integration**:

The bounded context will integrate with CODA's Link system patterns, providing typed identifier classes with flexible fallback patterns for institutional and contract identification.

**Migration Strategy**:

The bounded context will include standard data seeding for OpenCost identifier types following established CODA patterns.

## **Next Steps & Deliverables**

### **Immediate Action Items** 🎯

1. **Database Models Implementation** (Priority: Critical)
   - [ ] **Cost Sharing Models**:
     - [ ] `PublicationPositionCostShare` with validation constraints
     - [ ] Enhanced `Position` model with cost sharing methods
     - [ ] Business rule validation for cost share completeness
   - [ ] **OpenCost Report Models**:
     - [ ] `OpenCostReport` with status tracking and performance indexes
     - [ ] `OpenCostReportPublication` with audit trail snapshots
     - [ ] `OpenCostReportContract` and `OpenCostReportInvoice` models
   - [ ] **Contract Invoice Groups**:
     - [ ] `ContractInvoiceGroup` with period validation
     - [ ] `InvoiceGroupMembership` with contract consistency checks
     - [ ] Helper methods for group management and publication linking
   - [ ] **Identifier Systems**:
     - [ ] `InstitutionIdentifierType` & `InstitutionIdentifier` following CODA Link pattern
     - [ ] `ContractIdentifierType` & `ContractIdentifier` with URL formatting
     - [ ] Validation patterns and verification status tracking

2. **Database Migrations** (Priority: High)
   - [ ] **Phase 1 Migrations**: Core model creation with proper constraints
   - [ ] **Data Seeding**: Populate identifier types (ROR, ISNI, ESAC, etc.)
   - [ ] **Performance Indexes**: Add composite indexes for OpenCost bulk queries
   - [ ] **Constraint Testing**: Verify all database constraints work correctly
   - [ ] **Rollback Testing**: Ensure migrations can be safely reversed

3. **Development Environment Setup** (Priority: High)
   - [ ] Run migrations in development environment
   - [ ] Create sample data for testing (institutions with identifiers, cost sharing examples)
   - [ ] Set up admin interface for new models
   - [ ] Validate model relationships and constraints
   - [ ] Test bulk query performance with realistic data volumes

4. **Domain Integration** (Priority: Medium)
   - [ ] Create domain model conversion methods (`to_domain_object()`, `from_domain_object()`)
   - [ ] Implement repository pattern extensions for new models
   - [ ] Add domain-level validation for cost sharing arrangements
   - [ ] Create helper methods for OpenCost data extraction

5. **Testing Infrastructure** (Priority: Medium)
   - [ ] Unit tests for all model constraints and validation
   - [ ] Integration tests for domain-Django conversion
   - [ ] Performance tests for bulk query optimization
   - [ ] Migration tests for data consistency

### **Database Implementation Checklist** 📋

**Cost Sharing Implementation**:

- [ ] Create `PublicationPositionCostShare` model with all specified fields and constraints
- [ ] Add `clean()` method with currency validation logic
- [ ] Add database indexes for performance (`institution`, `position`, `created_at`)
- [ ] Add `validate_cost_share_completeness()` method to Position model
- [ ] Test constraint enforcement (publication-only, positive amounts, valid percentages)

**Identifier System Implementation**:

- [ ] Create identifier type models with validation regex patterns
- [ ] Add URL formatting methods for ROR, ISNI, ESAC identifiers
- [ ] Implement verification status tracking
- [ ] Add bulk lookup methods for OpenCost export
- [ ] Seed database with OpenCost-required identifier types

**Report Models Implementation**:

- [ ] Add report status tracking (generating, completed, failed)
- [ ] Implement snapshot audit trail for data consistency
- [ ] Add summary statistics fields for dashboard display
- [ ] Create proper foreign key relationships with cascading behavior
- [ ] Add performance indexes for report listing and filtering

**Contract Groups Implementation**:

- [ ] Add period validation constraints (start ≤ end)
- [ ] Implement contract-invoice consistency checking
- [ ] Add helper methods for automatic group creation (quarterly, yearly)
- [ ] Test group membership validation logic

### **Key Technical Decisions Made** ✅

- **Enhanced Database Design**: Added comprehensive field specifications, constraints, and validation
- **CODA Pattern Compliance**: Followed existing Link pattern for identifier management
- **Performance Optimization**: Strategic indexing for OpenCost bulk query scenarios
- **Migration Strategy**: Incremental approach with rollback capability and zero downtime
- **Audit Compliance**: Immutable snapshots with change tracking for regulatory requirements
- **Dedicated models**: Separate `InstitutionIdentifier` and `ContractIdentifier` models
- **Zero schema changes**: New identifier types require no database changes
- **Existing cost types**: Confirmed CODA's cost type system already supports OpenCost requirements

### **Critical Dependencies**

1. **OpenCost Schema**: `/app/src/coda/domain/opencost/` (✅ Ready)
2. **CODA Models**: Contract, Publication, Institution, Invoice (✅ Ready)
3. **Database**: PostgreSQL with Django ORM (✅ Ready)
4. **Phase 1.1 Completion**: Required before any transformation logic

### **Success Metrics**

- [ ] All Phase 1.1 models implemented and tested
- [ ] Zero breaking changes to existing CODA functionality
- [ ] Future OpenCost identifier types supported without schema changes
- [ ] Admin interface allows manual identifier management
- [ ] Ready for Phase 2 transformation service development

---

*This implementation plan follows CODA's established patterns and ensures the OpenCost reporting feature integrates seamlessly with the existing system while providing a future-proof foundation for identifier management.*

## **Technical Considerations**

### **Performance**

- Use bulk queries for large reports
- Cache XML generation for large reports
- Consider async processing for very large exports

### **Data Quality**

- Validate institution identifiers
- Handle missing DOIs gracefully
- Ensure cost data consistency

### **Extensibility**

- Design for additional export formats
- Support custom report filters
- Enable report templates

---

## **Appendix: Detailed Project Context**

*This section provides comprehensive technical context for developers and future project continuity.*

### **Project Background**

- **CODA**: Django-based system for managing publication costs, contracts, and institutional data
- **OpenCost**: XML schema standard for exchanging publication cost data between institutions
- **Goal**: Export CODA data in OpenCost XML format for institutional transparency and reporting
- **Deployment Model**: Single-institution CODA instances (no cross-institutional permission complexity)

### **Critical Domain Understanding**

#### **OpenCost Schema Requirements**

- **Publications**: Support `external_costsplitting` boolean field for multi-institutional cost sharing
- **Contracts**: Do NOT support cost splitting (confirmed via XSD analysis)
- **Institution Identifiers**: ROR, ISNI, Ringold supported in schema
- **Contract Identifiers**: ESAC (primary), OAI, EZB, local (secondary) supported
- **Contract Invoice Groups**: Billing period grouping concept for linking publications to contract periods
- **Date Formats**: Flexible YYYY, YYYY-MM, YYYY-MM-DD support required
- **Multiple Invoices**: Both publications and contracts can have multiple invoices (maxOccurs="unbounded")

#### **CODA Multi-Invoice Context**

- **CODA Reality**: Single publications/contracts often appear on multiple invoices (installments, split payments)
- **OpenCost Support**: Schema explicitly designed for multiple invoices per publication/contract
- **Implementation Need**: Report models must handle one-to-many relationships correctly

#### **CODA Architecture Patterns**

- **Invoice Bounded Context**: All cost management happens here, not in Publication domain
- **Domain-Driven Design**: Separate domain models from Django models with transformation layers
- **Link Pattern**: Existing flexible identifier system (`LinkType`/`Link`) serves as template
- **Cost Types**: Separate `PublicationCostType` and `ContractCostType` enums already OpenCost-compliant

### **Key Architectural Decisions**

#### **1. Report Data Consistency Strategy**

- **Problem**: Publication/invoice data changes after report generation, affecting report integrity
- **Solution**: Snapshot approach - store key display fields at report generation time + maintain navigation links
- **Rationale**: Institutional reporting requires audit-compliant immutable historical data

#### **2. Identifier System Architecture**

- **Problem**: Need flexible institution/contract identifiers for future OpenCost schema evolution
- **Solution**: Type/value pattern following CODA's Link system (no rigid enums)
- **Rationale**: OpenCost schema may add new identifier types without requiring database changes

#### **3. Cost Splitting Domain Scope**

- **Problem**: Where to implement multi-institutional cost sharing functionality
- **Solution**: Publication positions only, within invoice bounded context
- **Rationale**: OpenCost XSD analysis confirms contracts don't support cost splitting

#### **4. Multi-Invoice Support Strategy**

- **Problem**: CODA allows single publications/contracts to appear on multiple invoices; OpenCost must support this
- **Solution**: One-to-many relationships in report models + proper invoice grouping for contracts
- **Rationale**: OpenCost schema explicitly supports multiple invoices (maxOccurs="unbounded")

### **Common Pitfalls to Avoid**

- ❌ Adding cost splitting to contract positions (OpenCost doesn't support it)
- ❌ Storing cost splitting data in Publication model (belongs in invoice context)
- ❌ Using rigid enums for identifier types (prevents future OpenCost evolution)
- ❌ Assuming simple boolean for cost splitting (users need detailed financial tracking)
- ❌ Using live data links in reports (violates audit requirements for institutional reporting)
- ❌ Assuming one invoice per publication/contract (OpenCost supports multiple invoices)

### **Files & Integration Points**

- **OpenCost Schema**: `/app/src/coda/domain/opencost/opencost.xsd`
- **OpenCost Docs**: `/app/src/coda/domain/opencost/opencost_docs.md`
- **CODA Invoice Domain**: `/app/src/coda/domain/invoice.py`
- **CODA Link Pattern**: `/app/src/coda/apps/publications/models/_links.py`
- **Existing Domain Models**: `/app/src/coda/domain/opencost/_*.py`
