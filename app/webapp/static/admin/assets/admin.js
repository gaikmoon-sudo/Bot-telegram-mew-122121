(() => {
  'use strict';
  const tg = window.Telegram?.WebApp;
  tg?.ready(); tg?.expand();
  const initData = tg?.initData || '';
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state = { permissions: new Set(), roles: [], roleNames: [], permissionCatalog: [], adminRows: [], userId: null, section: null, page: 1, q: '', status: '', filter: '', loading: false };
  const permissionFor = {
    dashboard: ['admin.dashboard.view'], structure: ['courses.view','modules.view','lessons.view'], users: ['users.view'], courses: ['courses.view'], modules: ['modules.view'],
    lessons: ['lessons.view'], media: ['files.view','files.upload','videos.manage','videos.add_link','images.manage'],
    ai: ['ai.manage'], payments: ['payments.view','payments.manage'], certificates: ['certificates.manage'],
    notifications: ['notifications.manage'], admins: ['admins.manage','permissions.manage'], audit: ['security.logs.view'],
    bot: ['bot.settings'], settings: ['settings.manage']
  };
  const navGroups = [
    {title:'الرئيسية',items:[{id:'dashboard',label:'لوحة التحكم',icon:'◫'}]},
    {title:'إدارة المحتوى',items:[{id:'structure',label:'المخطط الهيكلي',icon:'⌘'},{id:'courses',label:'الدورات',icon:'▤'},{id:'modules',label:'الوحدات',icon:'▧'},{id:'lessons',label:'الدروس',icon:'▣'},{id:'media',label:'الملفات والفيديو',icon:'▱'}]},
    {title:'النظام',items:[{id:'users',label:'المستخدمون',icon:'◉'},{id:'ai',label:'إدارة الذكاء الاصطناعي',icon:'✳'},{id:'payments',label:'المدفوعات',icon:'◈'},{id:'certificates',label:'الشهادات',icon:'◇'},{id:'notifications',label:'الإشعارات',icon:'⌁'},{id:'admins',label:'المشرفون والصلاحيات',icon:'♙'},{id:'audit',label:'الأمان وسجل التدقيق',icon:'⛨'},{id:'bot',label:'إعدادات البوت',icon:'⌘'},{id:'settings',label:'إعدادات النظام',icon:'⚙'}]}
  ];
  const names = Object.fromEntries(navGroups.flatMap(g=>g.items.map(i=>[i.id,i.label])));

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (initData) headers.set('X-Telegram-Init-Data', initData);
    if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type','application/json');
    const response = await fetch(path, {...options, headers, credentials:'same-origin'});
    if (!response.ok) {
      const text = await response.text();
      let message = text;
      try { const obj = JSON.parse(text); message = obj.error || obj.message || text; } catch (_) {}
      if (response.status === 401) throw new Error('انتهت جلسة Telegram أو تعذّر التحقق منها. افتح اللوحة من داخل البوت.');
      if (response.status === 403) throw new Error('لا تملك الصلاحية اللازمة لهذا الإجراء.');
      throw new Error(message || `تعذر تنفيذ الطلب (${response.status})`);
    }
    const type = response.headers.get('content-type') || '';
    if (response.status === 204) return null;
    return type.includes('application/json') ? response.json() : response.text();
  }
  function can(key) { return state.permissions.has(key) || state.permissions.has('*.*'); }
  function canAny(keys) { return keys.some(can); }
  function toast(message, kind = 'success') {
    const node = document.createElement('div'); node.className = `toast toast-${kind}`;
    node.innerHTML = `<span class="toast-mark"></span><span>${esc(message)}</span>`;
    $('#toast-region').append(node); setTimeout(()=>node.remove(), 4200);
  }
  function navMarkup(filter = '') {
    const needle = filter.trim().toLocaleLowerCase('ar');
    return navGroups.map(group => {
      const items = group.items.filter(item => canAny(permissionFor[item.id] || []) && (!needle || item.label.toLocaleLowerCase('ar').includes(needle)));
      if (!items.length) return '';
      return `<section class="nav-group"><div class="nav-group-title">${esc(group.title)}</div>${items.map(item=>`<button class="nav-item ${state.section===item.id?'active':''}" data-section="${item.id}"><span class="nav-icon">${item.icon}</span><span>${esc(item.label)}</span></button>`).join('')}</section>`;
    }).join('');
  }
  function drawNavigation(filter='') {
    $('#navigation').innerHTML = navMarkup(filter);
    $$('.nav-item').forEach(button=>button.addEventListener('click',()=>openSection(button.dataset.section)));
  }
  function setAuthMessage(message, loading=false) {
    $('#auth-message').textContent = message;
    $('#auth-progress').classList.toggle('hidden',!loading);
  }
  async function boot() {
    try {
      if (!initData) throw new Error('يلزم فتح هذه الصفحة من داخل Telegram WebApp؛ لن تُعرض أي بيانات إدارية في المتصفح العادي.');
      const me = await api('/api/admin/session');
      state.permissions = new Set(me.permissions || []); state.userId = me.user_id; state.roleNames = me.roles || [];
      if (!state.permissions.size) throw new Error('هذا الحساب لا يحمل أي صلاحيات إدارية.');
      $('#profile-role').textContent = state.roleNames.map(roleLabel).join(' · ') || 'ADMIN';
      $('#profile-id').textContent = `ID ${state.userId}`;
      $('#profile-avatar').textContent = (state.roleNames[0] || 'A').slice(0,1);
      $('#auth-wall').classList.add('hidden'); $('#app-shell').classList.remove('hidden');
      drawNavigation();
      const first = navGroups.flatMap(group=>group.items).find(item=>canAny(permissionFor[item.id] || []));
      if (first) openSection(first.id);
      $('#nav-search').addEventListener('input',event=>drawNavigation(event.target.value));
      $('#menu-toggle').addEventListener('click',()=>toggleSidebar(true));
      $('#sidebar-close').addEventListener('click',()=>toggleSidebar(false));
      document.addEventListener('click',event=>{if(event.target.classList.contains('mobile-backdrop'))toggleSidebar(false)});
    } catch (error) { setAuthMessage(error.message, false); $('#auth-progress').classList.add('hidden'); }
  }
  function roleLabel(role) { return ({SUPER_ADMIN:'Super Admin',CONTENT_MANAGER:'مدير المحتوى',CONTENT_EDITOR:'محرر المحتوى'})[role] || role; }
  function toggleSidebar(open) {
    $('#sidebar').classList.toggle('open',open);
    let backdrop=$('.mobile-backdrop');
    if(open && !backdrop){backdrop=document.createElement('div');backdrop.className='mobile-backdrop';document.body.append(backdrop);backdrop.addEventListener('click',()=>toggleSidebar(false));}
    backdrop?.classList.toggle('show',open);
  }
  function openSection(section) {
    if (!canAny(permissionFor[section] || [])) { toast('هذا القسم غير متاح لحسابك.','error'); return; }
    state.section=section;state.page=1;state.q='';state.status='';state.filter='';
    drawNavigation($('#nav-search').value);
    $('#crumb-title').textContent=names[section] || section;
    toggleSidebar(false);
    renderSection();
  }
  function heading(title, description, actions='') {
    return `<div class="page-heading"><div><div class="eyebrow">TECH ACADEMY / ${esc(state.section).toUpperCase()}</div><h1>${esc(title)}</h1><p>${esc(description)}</p></div><div class="heading-actions">${actions}</div></div>`;
  }
  function loadingBlock() { $('#main-content').innerHTML = `<div class="loading-block"><span class="spinner"></span>&nbsp; جارٍ تحميل البيانات…</div>`; }
  async function renderSection() {
    loadingBlock();
    try {
      switch(state.section){
        case 'dashboard': return await renderDashboard();
        case 'structure': return await renderStructure();
        case 'courses': return await renderCourses();
        case 'modules': return await renderModules();
        case 'lessons': return await renderLessons();
        case 'media': return await renderMedia();
        case 'admins': return await renderRoles();
        case 'audit': return await renderAudit();
        default: return renderPlaceholder();
      }
    } catch(error) { $('#main-content').innerHTML=heading(names[state.section]||'الإدارة','')+`<div class="empty-state"><div class="empty-icon">!</div><h3>تعذر تحميل البيانات</h3><p>${esc(error.message)}</p><button class="button button-primary" id="retry-button">إعادة المحاولة</button></div>`;$('#retry-button')?.addEventListener('click',renderSection); }
  }
  async function renderDashboard() {
    const d=await api('/api/admin/dashboard');
    const metrics=[['إجمالي الدورات',d.courses,'▤','ضمن المسارات التعليمية'],['الوحدات',d.modules,'▧','وحدات منظّمة'],['الدروس',d.lessons,'▣','محتوى محفوظ'],['دروس منشورة',d.published_lessons,'◉','حالة النشر الحالية']];
    const health=d.service_health||{};
    const healthCard=Object.entries({database:'PostgreSQL',redis:'Redis',telegram:'Telegram API'}).map(([key,label])=>`<span class="status-pill ${health[key]?'status-published':'status-draft'}">${health[key]?'●':'○'} ${label}: ${health[key]?'متصل':'تحقق مطلوب'}</span>`).join('');
    $('#main-content').innerHTML=heading('لوحة التحكم','نظرة موجزة على المحتوى ونشاط مساحة الإدارة.')+`<div class="metric-grid">${metrics.map(m=>`<article class="metric-card"><div class="metric-top"><span>${m[0]}</span><span class="metric-icon">${m[2]}</span></div><div class="metric-number">${Number(m[1]||0).toLocaleString('ar')}</div><div class="metric-foot">${m[3]}</div></article>`).join('')}</div><section class="panel" style="margin-bottom:14px"><div class="panel-header"><div><h2>حالة المنصة</h2><p>فحص مباشر للخدمات الأساسية قبل النشر</p></div><span class="status-pill ${Object.values(health).every(Boolean)?'status-published':'status-draft'}">${Object.values(health).every(Boolean)?'جاهزة':'تحتاج مراجعة'}</span></div><div class="panel-body" style="display:flex;gap:8px;flex-wrap:wrap">${healthCard}</div></section><div class="dashboard-grid"><section class="panel"><div class="panel-header"><div><h2>الأكثر مشاهدة وإكمالًا</h2><p>إحصاءات حقيقية من تقدم المتعلمين</p></div></div><div class="panel-body"><div class="stats-list">${(d.lesson_stats||[]).map(item=>`<div class="stats-row"><strong>${esc(item.title)}</strong><span>مشاهدة ${item.views} · مكتمل ${item.completed}</span></div>`).join('')||'<p>لا توجد بيانات تقدم بعد.</p>'}</div></div></section><section class="panel"><div class="panel-header"><div><h2>الانتقال السريع</h2><p>أدوات المحتوى المتاحة لصلاحياتك</p></div></div><div class="panel-body"><div class="quick-actions">${[['courses','إنشاء دورة','ابدأ تنظيم مسار جديد','＋','courses.create'],['modules','إضافة وحدة','نظّم محتوى الدورة','▧','modules.create'],['lessons','إضافة درس','أضف محتوى تعليميًا','▣','lessons.create'],['media','الملفات والفيديو','اربط موارد الدرس','▱','files.upload']].filter(x=>can(x[4])).map(x=>`<button class="quick-action" data-go="${x[0]}"><span class="quick-action-icon">${x[3]}</span><span><strong>${x[1]}</strong><small>${x[2]}</small></span></button>`).join('')||'<p>لا توجد إجراءات سريعة متاحة.</p>'}</div></div></section></div>`;
    $$('[data-go]').forEach(b=>b.addEventListener('click',()=>openSection(b.dataset.go)));
  }
  function statusPill(status) { const key=String(status||'DRAFT').toUpperCase();const cls=key==='PUBLISHED'?'status-published':key==='DRAFT'?'status-draft':'';const label=({PUBLISHED:'منشور',DRAFT:'مسودة',IN_REVIEW:'قيد المراجعة',APPROVED:'معتمد',ARCHIVED:'مؤرشف'})[key]||key;return `<span class="status-pill ${cls}">${label}</span>`; }
  function toolbar({search=true,status=true,select='',selectOptions=[]}={}) { return `<div class="toolbar">${search?'<label class="search-box"><input id="table-search" type="search" value="'+esc(state.q)+'" placeholder="ابحث بالعنوان أو الاسم…" /></label>':''}${select?`<select class="filter-select" id="entity-filter"><option value="">${esc(select)}</option>${selectOptions.map(o=>`<option value="${esc(o.id)}" ${state.filter===o.id?'selected':''}>${esc(o.title)}</option>`).join('')}</select>`:''}${status?`<select class="filter-select" id="status-filter"><option value="">كل الحالات</option><option value="DRAFT" ${state.status==='DRAFT'?'selected':''}>مسودة</option><option value="PUBLISHED" ${state.status==='PUBLISHED'?'selected':''}>منشور</option><option value="IN_REVIEW" ${state.status==='IN_REVIEW'?'selected':''}>قيد المراجعة</option><option value="ARCHIVED" ${state.status==='ARCHIVED'?'selected':''}>مؤرشف</option></select>`:''}</div>`; }
  function attachFilters() {
    const search=$('#table-search');search?.addEventListener('keydown',event=>{if(event.key==='Enter'){state.q=search.value.trim();state.page=1;renderSection()}});
    const status=$('#status-filter');status?.addEventListener('change',()=>{state.status=status.value;state.page=1;renderSection()});
    const filter=$('#entity-filter');filter?.addEventListener('change',()=>{state.filter=filter.value;state.page=1;renderSection()});
  }
  function pagination(data) { const pages=data.pages||0;return `<div class="pagination"><span>النتائج ${data.total?((data.page-1)*data.page_size+1):0}–${Math.min(data.page*data.page_size,data.total)} من ${Number(data.total||0).toLocaleString('ar')}</span><div class="pagination-controls"><button data-page="prev" ${data.page<=1?'disabled':''} aria-label="السابق">‹</button><span>${data.page} / ${Math.max(1,pages)}</span><button data-page="next" ${data.page>=pages?'disabled':''} aria-label="التالي">›</button></div></div>`; }
  function attachPagination(data) { $$('[data-page]').forEach(b=>b.addEventListener('click',()=>{if(b.disabled)return;state.page+=b.dataset.page==='next'?1:-1;renderSection()})); }
  function emptyState(title,desc,button='') { return `<div class="empty-state"><div class="empty-icon">◌</div><h3>${esc(title)}</h3><p>${esc(desc)}</p>${button}</div>`; }
  function rowOrder(id,parentId){if(!can('content.order'))return '';return `<span class="order-buttons"><button class="icon-button" data-move="up" data-id="${esc(id)}" data-parent="${esc(parentId)}" aria-label="تحريك للأعلى">↑</button><button class="icon-button" data-move="down" data-id="${esc(id)}" data-parent="${esc(parentId)}" aria-label="تحريك للأسفل">↓</button></span>`;}
  async function loadPage(resource, params={}) { const q=new URLSearchParams({page:String(state.page),page_size:'20',q:state.q,status:state.status,...params});return api(`/api/admin/${resource}?${q}`); }
  async function renderStructure(){
    const [paths,courses,modules,lessons]=await Promise.all([
      api('/api/admin/learning-paths?page_size=100'),
      api('/api/admin/courses?page_size=100'),
      api('/api/admin/modules?page_size=100'),
      api('/api/admin/lessons?page_size=100')
    ]);
    const pathRows=paths.items||[], courseRows=courses.items||[], moduleRows=modules.items||[], lessonRows=lessons.items||[];
    const by=(rows,key)=>rows.reduce((m,row)=>{(m[row[key]] ||= []).push(row);return m},{});
    const coursesByPath=by(courseRows,'learning_path_id'), modulesByCourse=by(moduleRows,'course_id'), lessonsByModule=by(lessonRows,'module_id');
    const node=(kind,title,meta,children='',actions='',attrs='')=>`<article class="structure-node structure-${kind}" ${attrs}><div class="structure-node-main"><span class="structure-marker">${kind==='path'?'◆':kind==='course'?'▤':kind==='module'?'▧':kind==='lesson'?'▣':'▶'}</span><div class="structure-node-copy"><strong>${esc(title)}</strong><small>${esc(meta||'')}</small></div>${actions}</div>${children?`<div class="structure-children">${children}</div>`:''}</article>`;
    const add=(type,parentId,label)=>`<button class="button button-small structure-add" data-add-node="${type}" data-parent-id="${esc(parentId||'')}">＋ ${label}</button>`;
    const lessonNode=lesson=>{
      const links=lesson.content_metadata?.video_links||[], files=[...(lesson.content_metadata?.assets||[]),...(lesson.content_metadata?.images||[])];
      const resources=[...links.map(v=>node('video',v.label||'فيديو',v.url,'',`${can('videos.manage')?`<button class="button button-small structure-edit" data-edit-video="${esc(v.id)}" data-video-lesson="${esc(lesson.id)}" data-video-url="${esc(v.url)}" data-video-label="${esc(v.label||'فيديو')}">تعديل</button>`:''}<span class="structure-status">رابط</span>`)),...files.map(f=>node('file',f.filename||'ملف',f.content_type||'ملف','',`<span class="structure-status">${formatBytes(f.size||0)}</span>`))].join('');
      return node('lesson',lesson.title,`${lesson.status} · v${lesson.version||1}`,resources,`${statusPill(lesson.status)} <button class="button button-small structure-edit" data-edit-lesson="${esc(lesson.id)}">تعديل</button> <button class="button button-small" data-preview-structure="${esc(lesson.id)}">معاينة Telegram</button> <button class="button button-small" data-compare-versions="${esc(lesson.id)}">مقارنة الإصدارات</button> ${can('lessons.create')?add('lesson',lesson.module_id,'درس'):''}`, `data-node-id="${esc(lesson.id)}" data-parent-id="${esc(lesson.module_id)}"`);
    };
    const moduleNode=module=>node('module',module.title,`${module.lesson_count||0} درس · ${module.status}`, (lessonsByModule[module.id]||[]).map(lessonNode).join('') || `<div class="structure-empty">لا توجد دروس بعد. ${can('lessons.create')?add('lesson',module.id,'إضافة درس'):''}</div>`, `${statusPill(module.status)} <button class="button button-small structure-edit" data-edit-module="${esc(module.id)}">تعديل</button> ${can('modules.create')?add('module',module.course_id,'وحدة'):''}`, `data-node-id="${esc(module.id)}" data-parent-id="${esc(module.course_id)}"`);
    const courseNode=course=>node('course',course.title,`${course.module_count||0} وحدة · ${course.status}`, (modulesByCourse[course.id]||[]).map(moduleNode).join('') || `<div class="structure-empty">لا توجد وحدات بعد. ${can('modules.create')?add('module',course.id,'إضافة وحدة'):''}</div>`, `${statusPill(course.status)} <button class="button button-small structure-edit" data-edit-course="${esc(course.id)}">تعديل</button> <button class="button button-small" data-course-rel="${esc(course.id)}">المتطلبات</button> <button class="button button-small" data-copy-course="${esc(course.id)}">نسخ</button> ${can('courses.create')?add('course',course.learning_path_id,'دورة'):''}`, `data-node-id="${esc(course.id)}" data-parent-id="${esc(course.learning_path_id)}"`);
    const pathNode=path=>node('path',path.title,`${(coursesByPath[path.id]||[]).length} دورة · ${path.status}`, (coursesByPath[path.id]||[]).map(courseNode).join('') || `<div class="structure-empty">لا توجد دورات بعد. ${can('courses.create')?add('course',path.id,'إضافة دورة'):''}</div>`, `${statusPill(path.status)} ${can('courses.create')?add('course',path.id,'دورة'):''}<button class="button button-small" data-validate-path="${esc(path.id)}">فحص</button><button class="button button-small" data-publish-path="${esc(path.id)}">نشر المسار</button>`, `data-node-id="${esc(path.id)}" data-parent-id=""`);
    const tree=pathRows.map(pathNode).join('');
    $('#main-content').innerHTML=heading('المخطط الهيكلي','اختر المكان من الخريطة ثم أضف أو عدّل المحتوى؛ التغييرات المحفوظة في الدروس تُزامن مع بوت Telegram.',`${can('courses.create')?'<button class="button button-primary" id="structure-new-path">＋ مسار رئيسي</button>':''}<button class="button button-primary" id="open-holographic">✦ الخريطة الهولوغرامية</button><button class="button button-quiet" id="structure-fullscreen">⛶ ملء الشاشة</button><button class="button button-quiet" id="structure-refresh">↻ تحديث</button>`)+`<div class="structure-toolbar"><label class="search-box structure-search"><input id="structure-search" type="search" placeholder="ابحث داخل كل المسارات…" /></label><button class="button button-small" id="structure-expand">＋ توسيع الكل</button><button class="button button-small" id="structure-collapse">− طي الكل</button><button class="button button-small structure-view-toggle" id="structure-view">◈ عرض ثلاثي الأبعاد</button></div><div class="structure-legend"><span>◆ مسار</span><span>▤ دورة</span><span>▧ وحدة</span><span>▣ درس</span><span>▶ فيديو</span><span>↧ ملف</span><span>◌ طبقة زمنية للإصدارات</span></div><section class="structure-board">${tree||emptyState('لا يوجد هيكل بعد','ابدأ بإنشاء مسار تعلّم رئيسي.')}</section>`;
    $('#structure-new-path')?.addEventListener('click',()=>createPath());$('#open-holographic')?.addEventListener('click',()=>window.location.assign('/admin/holographic/'));$('#structure-refresh')?.addEventListener('click',renderStructure);
    $('#structure-fullscreen')?.addEventListener('click',async()=>{const board=$('.structure-board');try{if(!document.fullscreenElement)await board.requestFullscreen();else await document.exitFullscreen()}catch(_){board.classList.toggle('structure-fullscreen')}});
    $$('[data-validate-path]').forEach(b=>b.addEventListener('click',async()=>{const result=await api(`/api/admin/learning-paths/${b.dataset.validatePath}/validate`);toast(result.valid?'المسار مكتمل وجاهز للنشر':`يحتاج المسار إلى ${result.errors.length} إصلاحات`,result.valid?'success':'error')}));
    $$('[data-publish-path]').forEach(b=>b.addEventListener('click',()=>confirmAction('نشر المسار بالكامل؟','سيتم نشر المسار ودوراته ووحداته ودروسه بعد التحقق من اكتمال المحتوى.',async()=>{await api(`/api/admin/learning-paths/${b.dataset.publishPath}/publish`,{method:'POST'});toast('تم نشر المسار بالكامل');renderStructure()})));

    const board=$('.structure-board'), saved3d=localStorage.getItem('academy-structure-3d')==='1';
    const set3d=enabled=>{board?.classList.toggle('structure-3d',enabled);localStorage.setItem('academy-structure-3d',enabled?'1':'0');const view=$('#structure-view');if(view)view.textContent=enabled?'▣ عرض مسطح':'◈ عرض ثلاثي الأبعاد';};
    set3d(saved3d);$('#structure-view')?.addEventListener('click',()=>set3d(!board.classList.contains('structure-3d')));
    $('#structure-expand')?.addEventListener('click',()=>$$('.structure-children',board).forEach(x=>x.classList.remove('structure-collapsed')));
    $('#structure-collapse')?.addEventListener('click',()=>$$('.structure-children',board).forEach(x=>x.classList.add('structure-collapsed')));
    $('#structure-search')?.addEventListener('input',event=>{const query=event.target.value.trim().toLocaleLowerCase('ar');$$('.structure-node',board).forEach(x=>x.classList.toggle('structure-hidden',Boolean(query&&!x.textContent.toLocaleLowerCase('ar').includes(query))))});
    $$('.structure-edit').forEach(button=>button.addEventListener('click',()=>button.dataset.editCourse?editCourse(courseRows.find(x=>x.id===button.dataset.editCourse)):button.dataset.editModule?editModule(moduleRows.find(x=>x.id===button.dataset.editModule)):editLesson(button.dataset.editLesson)));
    $$('[data-edit-video]').forEach(button=>button.addEventListener('click',()=>editStructureVideo(button.dataset)));
    $$('[data-course-rel]').forEach(button=>button.addEventListener('click',()=>editCourseRelationships(button.dataset.courseRel,courseRows)));
    $$('[data-copy-course]').forEach(button=>button.addEventListener('click',()=>copyStructureCourse(button.dataset.copyCourse,courseRows.find(x=>x.id===button.dataset.copyCourse))));
    $$('[data-preview-structure]').forEach(button=>button.addEventListener('click',()=>previewTelegramLesson(button.dataset.previewStructure)));
    $$('[data-compare-versions]').forEach(button=>button.addEventListener('click',()=>compareLessonVersions(button.dataset.compareVersions)));
    $$('.structure-add').forEach(button=>button.addEventListener('click',()=>{const type=button.dataset.addNode,id=button.dataset.parentId;if(type==='course')createCourse(pathRows,id);else if(type==='module')createModule(courseRows,id);else createLesson(moduleRows,id)}));
    let dragged=null;
    $$('.structure-node.structure-course,.structure-node.structure-module,.structure-node.structure-lesson').forEach(node=>{node.draggable=true;node.addEventListener('dragstart',event=>{dragged=node;event.dataTransfer.effectAllowed='move';node.classList.add('structure-dragging')});node.addEventListener('dragend',()=>{dragged?.classList.remove('structure-dragging');dragged=null});node.addEventListener('dragover',event=>{if(dragged&&dragged.className.split(' ').some(c=>c===node.className.split(' ')[1])){event.preventDefault();node.classList.add('structure-drop-target')}});node.addEventListener('dragleave',()=>node.classList.remove('structure-drop-target'));node.addEventListener('drop',async event=>{event.preventDefault();node.classList.remove('structure-drop-target');if(!dragged||dragged===node)return;const kind=node.classList.contains('structure-course')?'courses':node.classList.contains('structure-module')?'modules':'lessons';const parent=dragged.dataset.parentId;const siblings=[...node.parentElement.children].filter(x=>x.dataset?.nodeId&&x.classList.contains(`structure-${kind.slice(0,-1)}`));const ordered=siblings.map(x=>x.dataset.nodeId);const from=ordered.indexOf(dragged.dataset.nodeId),to=ordered.indexOf(node.dataset.nodeId);if(from<0||to<0)return;ordered.splice(from,1);ordered.splice(to,0,dragged.dataset.nodeId);try{await api(`/api/admin/${kind}/order`,{method:'POST',body:JSON.stringify({parent_id:parent,ordered_ids:ordered})});toast('تم حفظ الترتيب');renderStructure()}catch(error){toast(error.message,'error')}})});

  }

  async function editStructureVideo(data){await showForm({title:'تعديل رابط الفيديو',fields:[{name:'label',label:'اسم الفيديو',value:data.videoLabel||'فيديو'},{name:'url',label:'رابط HTTPS',value:data.videoUrl||'',required:true}],onSubmit:async payload=>{await api(`/api/admin/lessons/${data.videoLesson}/videos/${data.editVideo}`,{method:'PATCH',body:JSON.stringify(payload)});toast('تم تحديث رابط الفيديو');renderStructure()}})}

  async function editCourseRelationships(id,rows){const current=await api(`/api/admin/courses/${id}/relationships`);await showForm({title:'متطلبات الدورة',fields:[{name:'prerequisite_ids',label:'الدورات المطلوبة قبل البدء',type:'multiselect',value:(current.prerequisites||[]).map(x=>x.id),options:rows.filter(x=>x.id!==id).map(x=>({value:x.id,label:x.title}))}],onSubmit:async payload=>{await api(`/api/admin/courses/${id}/relationships`,{method:'PUT',body:JSON.stringify(payload)});toast('تم تحديث متطلبات الدورة');renderStructure()}})}
  async function copyStructureCourse(id,row){await showForm({title:'نسخ دورة كاملة',fields:[{name:'title',label:'عنوان النسخة الجديدة',value:`${row?.title||'دورة'} — نسخة`,required:true}],onSubmit:async payload=>{await api(`/api/admin/courses/${id}/copy`,{method:'POST',body:JSON.stringify(payload)});toast('تم نسخ الدورة مع الوحدات والدروس والموارد');renderStructure()}})}
  async function previewTelegramLesson(id){const row=await api(`/api/admin/lessons/${id}/preview`);$('#preview-title').textContent=`معاينة Telegram · ${row.title}`;const body=$('#preview-content');body.replaceChildren();const bubble=document.createElement('div');bubble.className='telegram-preview-bubble';bubble.textContent=row.content_body||'لا يوجد محتوى';body.append(bubble);(row.content_metadata?.video_links||[]).forEach(item=>{const link=document.createElement('a');link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';link.className='telegram-preview-link';link.textContent=`▶ ${item.label||'فيديو'}`;body.append(link)});$('#preview-dialog').showModal()}
  async function compareLessonVersions(id){const versions=await api(`/api/admin/lessons/${id}/versions`);$('#preview-title').textContent='مقارنة إصدارات الدرس';const body=$('#preview-content');body.replaceChildren();if(!versions.length){body.textContent='لا توجد إصدارات';}else{const grid=document.createElement('div');grid.className='version-compare-grid';versions.slice(0,2).forEach(item=>{const card=document.createElement('article');card.className='version-card';card.innerHTML=`<strong>الإصدار ${esc(item.version)}</strong><small>${esc(item.change_summary||'—')} · ${esc(item.status)}</small>`;const text=document.createElement('p');text.textContent=item.content_body;card.append(text);grid.append(card)});body.append(grid)}$('#preview-dialog').showModal()}

  async function renderCourses() {
    const [paths,data]=await Promise.all([api('/api/admin/learning-paths?page_size=100'),loadPage('courses')]);
    const actions=`${can('courses.create')?'<button class="button button-quiet" id="new-path">＋ مسار تعلّم</button><button class="button button-primary" id="new-course">＋ إنشاء دورة</button>':''}`;
    $('#main-content').innerHTML=heading('الدورات','أنشئ الدورات واربطها بمسار التعلّم، ثم تابع ترتيبها وحالتها.',actions)+toolbar({status:true})+(data.items.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>الدورة</th><th>المسار</th><th>الوحدات</th><th>الحالة</th><th>الترتيب</th><th>إجراءات</th></tr></thead><tbody>${data.items.map((r,i)=>`<tr><td class="primary-cell">${esc(r.title)}<span class="secondary-cell">${esc(r.slug)}</span></td><td>${esc(r.learning_path_title)}</td><td>${r.module_count}</td><td>${statusPill(r.status)}</td><td>${rowOrder(r.id,r.learning_path_id)}</td><td><div class="row-actions">${can('courses.edit')?`<button class="button button-small" data-edit="${esc(r.id)}">تعديل</button>`:''}${can('courses.delete')?`<button class="button button-small button-danger" data-delete="${esc(r.id)}" data-title="${esc(r.title)}">حذف</button>`:''}</div></td></tr>`).join('')}</tbody></table></div>${pagination(data)}`:emptyState('لا توجد دورات بعد','أنشئ مسار تعلّم أولًا، ثم أضف أول دورة.',can('courses.create')?'<button class="button button-primary" id="empty-course">إنشاء دورة</button>':''));
    attachFilters();attachPagination(data);$('#new-path')?.addEventListener('click',createPath);$('#new-course')?.addEventListener('click',()=>createCourse(paths.items));$('#empty-course')?.addEventListener('click',()=>createCourse(paths.items));
    $$('[data-edit]').forEach(b=>b.addEventListener('click',()=>editCourse(data.items.find(x=>x.id===b.dataset.edit))));
    $$('[data-delete]').forEach(b=>b.addEventListener('click',()=>confirmAction('حذف الدورة؟',`سيؤدي هذا إلى حذف «${b.dataset.title}» ووحداتها ودروسها التابعة. لا يمكن التراجع عن ذلك.`,async()=>{await api(`/api/admin/courses/${b.dataset.delete}`,{method:'DELETE'});toast('تم حذف الدورة');renderSection()})));
    attachOrdering('courses',data.items,'learning_path_id');
  }
  async function createPath(){await showForm({title:'إنشاء مسار تعلّم',fields:[{name:'title',label:'اسم المسار',required:true},{name:'description',label:'الوصف',type:'textarea'}],onSubmit:async data=>{await api('/api/admin/learning-paths',{method:'POST',body:JSON.stringify(data)});toast('تم إنشاء مسار التعلّم');renderSection()}})}
  async function createCourse(paths, selectedPathId=''){if(!paths.length){toast('أنشئ مسار تعلّم أولًا.','error');return createPath()}await showForm({title:'إنشاء دورة',fields:[{name:'title',label:'عنوان الدورة',required:true},{name:'learning_path_id',label:'مسار التعلّم (المكان المحدد)',type:'select',required:true,value:selectedPathId,options:paths.map(x=>({value:x.id,label:x.title}))},{name:'summary',label:'ملخص الدورة',type:'textarea'},{name:'status',label:'الحالة',type:'select',value:'DRAFT',options:statuses()}],onSubmit:async data=>{await api('/api/admin/courses',{method:'POST',body:JSON.stringify(data)});toast('تم إنشاء الدورة');renderSection()}})}
  async function editCourse(row){await showForm({title:'تعديل الدورة',fields:[{name:'title',label:'عنوان الدورة',value:row.title,required:true},{name:'summary',label:'ملخص الدورة',type:'textarea',value:row.summary||''},{name:'position',label:'الترتيب',type:'number',value:row.position},{name:'status',label:'الحالة',type:'select',value:row.status,options:statuses()}],onSubmit:async data=>{await api(`/api/admin/courses/${row.id}`,{method:'PATCH',body:JSON.stringify(data)});toast('تم تحديث الدورة');renderSection()}})}
  async function renderModules() {
    const courses=await api('/api/admin/courses?page_size=100');
    const data=await loadPage('modules',state.filter?{course_id:state.filter}:{});
    const actions=can('modules.create')?'<button class="button button-primary" id="new-module">＋ إنشاء وحدة</button>':'';
    $('#main-content').innerHTML=heading('الوحدات','نظّم الدورة إلى وحدات تعليمية واضحة.',actions)+toolbar({status:true,select:'كل الدورات',selectOptions:courses.items.map(x=>({id:x.id,title:x.title}))})+(data.items.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>الوحدة</th><th>الدورة</th><th>الدروس</th><th>الحالة</th><th>الترتيب</th><th>إجراءات</th></tr></thead><tbody>${data.items.map((r,i)=>`<tr><td class="primary-cell">${esc(r.title)}<span class="secondary-cell">${esc(r.slug)}</span></td><td>${esc(r.course_title)}</td><td>${r.lesson_count}</td><td>${statusPill(r.status)}</td><td>${rowOrder(r.id,r.course_id)}</td><td><div class="row-actions">${can('modules.edit')?`<button class="button button-small" data-edit="${r.id}">تعديل</button>`:''}${can('modules.delete')?`<button class="button button-small button-danger" data-delete="${r.id}" data-title="${esc(r.title)}">حذف</button>`:''}</div></td></tr>`).join('')}</tbody></table></div>${pagination(data)}`:emptyState('لا توجد وحدات مطابقة','اختر دورة أو أنشئ أول وحدة للمحتوى.',can('modules.create')?'<button class="button button-primary" id="empty-module">إنشاء وحدة</button>':''));
    attachFilters();attachPagination(data);$('#new-module')?.addEventListener('click',()=>createModule(courses.items));$('#empty-module')?.addEventListener('click',()=>createModule(courses.items));
    $$('[data-edit]').forEach(b=>b.addEventListener('click',()=>editModule(data.items.find(x=>x.id===b.dataset.edit))));
    $$('[data-delete]').forEach(b=>b.addEventListener('click',()=>confirmAction('حذف الوحدة؟',`سيؤدي ذلك إلى حذف «${b.dataset.title}» والدروس التابعة لها.`,async()=>{await api(`/api/admin/modules/${b.dataset.delete}`,{method:'DELETE'});toast('تم حذف الوحدة');renderSection()})));
    attachOrdering('modules',data.items,'course_id');
  }
  function statuses(){return [{value:'DRAFT',label:'مسودة'},{value:'IN_REVIEW',label:'قيد المراجعة'},{value:'APPROVED',label:'معتمد'},{value:'PUBLISHED',label:'منشور'},{value:'ARCHIVED',label:'مؤرشف'}]}
  async function createModule(courses, selectedCourseId=''){if(!courses.length){toast('أنشئ دورة أولًا.','error');openSection('courses');return}await showForm({title:'إنشاء وحدة',fields:[{name:'title',label:'عنوان الوحدة',required:true},{name:'course_id',label:'الدورة (المكان المحدد)',type:'select',required:true,value:selectedCourseId,options:courses.map(x=>({value:x.id,label:x.title}))},{name:'description',label:'الوصف',type:'textarea'},{name:'status',label:'الحالة',type:'select',value:'DRAFT',options:statuses()}],onSubmit:async data=>{await api('/api/admin/modules',{method:'POST',body:JSON.stringify(data)});toast('تم إنشاء الوحدة');renderSection()}})}
  async function editModule(row){const courses=await api('/api/admin/courses?page_size=100');await showForm({title:'تعديل الوحدة',fields:[{name:'title',label:'عنوان الوحدة',value:row.title,required:true},{name:'description',label:'الوصف',type:'textarea',value:row.description||''},{name:'position',label:'الترتيب',type:'number',value:row.position},{name:'status',label:'الحالة',type:'select',value:row.status,options:statuses()}],onSubmit:async data=>{await api(`/api/admin/modules/${row.id}`,{method:'PATCH',body:JSON.stringify(data)});toast('تم تحديث الوحدة');renderSection()}})}
  async function renderLessons(){
    const modules=can('lessons.create')?await api('/api/admin/modules?page_size=100'):{items:[]};
    const data=await loadPage('lessons',state.filter?{module_id:state.filter}:{});
    const actions=can('lessons.create')?'<button class="button button-primary" id="new-lesson">＋ إنشاء درس</button>':'';
    $('#main-content').innerHTML=heading('الدروس','حرّر المحتوى، راجع الإصدارات، وتابع حالة النشر.',actions)+toolbar({status:true,select:'كل الوحدات',selectOptions:modules.items.map(x=>({id:x.id,title:x.title}))})+(data.items.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>الدرس</th><th>الوحدة / الدورة</th><th>الإصدار</th><th>الحالة</th><th>الترتيب</th><th>إجراءات</th></tr></thead><tbody>${data.items.map((r,i)=>`<tr><td class="primary-cell">${esc(r.title)}<span class="secondary-cell">${esc(r.summary||'—')}</span></td><td>${esc(r.module_title)}<span class="secondary-cell">${esc(r.course_title)}</span></td><td>v${r.version||1}</td><td>${statusPill(r.status)}</td><td>${rowOrder(r.id,r.module_id)}</td><td><div class="row-actions"><button class="button button-small" data-preview="${r.id}">معاينة</button>${can('lessons.edit')?`<button class="button button-small" data-edit="${r.id}">تعديل</button>`:''}${can('lessons.delete')?`<button class="button button-small button-danger" data-delete="${r.id}" data-title="${esc(r.title)}">حذف</button>`:''}</div></td></tr>`).join('')}</tbody></table></div>${pagination(data)}`:emptyState('لا توجد دروس مطابقة','أضف درسًا جديدًا أو غيّر البحث والتصفية.',can('lessons.create')?'<button class="button button-primary" id="empty-lesson">إنشاء درس</button>':''));
    attachFilters();attachPagination(data);$('#new-lesson')?.addEventListener('click',()=>createLesson(modules.items));$('#empty-lesson')?.addEventListener('click',()=>createLesson(modules.items));
    $$('[data-preview]').forEach(b=>b.addEventListener('click',()=>previewLesson(b.dataset.preview)));
    $$('[data-edit]').forEach(b=>b.addEventListener('click',()=>editLesson(b.dataset.edit)));
    $$('[data-delete]').forEach(b=>b.addEventListener('click',()=>confirmAction('حذف الدرس؟',`سيتم حذف «${b.dataset.title}» وإصداراته. لا يمكن التراجع عن ذلك.`,async()=>{await api(`/api/admin/lessons/${b.dataset.delete}`,{method:'DELETE'});toast('تم حذف الدرس');renderSection()})));
    attachOrdering('lessons',data.items,'module_id');
  }
  async function createLesson(modules, selectedModuleId=''){if(!modules.length){toast('أنشئ وحدة أولًا.','error');openSection('modules');return}await showForm({title:'إنشاء درس',fields:[{name:'title',label:'عنوان الدرس',required:true},{name:'module_id',label:'الوحدة (المكان المحدد)',type:'select',required:true,value:selectedModuleId,options:modules.map(x=>({value:x.id,label:`${x.course_title} — ${x.title}`}))},{name:'summary',label:'ملخص قصير',type:'textarea'},{name:'content_body',label:'محتوى الدرس',type:'textarea',required:true},{name:'status',label:'الحالة',type:'select',value:'DRAFT',options:statuses()}],onSubmit:async data=>{await api('/api/admin/lessons',{method:'POST',body:JSON.stringify(data)});toast('تم إنشاء الدرس');renderSection()}})}
  async function editLesson(id){const row=await api(`/api/admin/lessons/${id}`);await showForm({title:`تعديل: ${row.title}`,fields:[{name:'title',label:'عنوان الدرس',value:row.title,required:true},{name:'summary',label:'ملخص قصير',type:'textarea',value:row.summary||''},{name:'content_body',label:'محتوى الدرس',type:'textarea',value:row.content_body||'',required:true},{name:'change_summary',label:'ملخص التغيير',value:'تحديث عبر Admin Panel'},{name:'status',label:'الحالة',type:'select',value:row.status,options:statuses()}],onSubmit:async data=>{await api(`/api/admin/lessons/${id}`,{method:'PATCH',body:JSON.stringify(data)});toast('تم حفظ الدرس كإصدار جديد');renderSection()}})}
  async function previewLesson(id){const row=await api(`/api/admin/lessons/${id}/preview`);$('#preview-title').textContent=row.title;const body=$('#preview-content');body.replaceChildren();const text=document.createElement('div');text.textContent=row.content_body||'لا يوجد محتوى نصي.';body.append(text);const links=row.content_metadata?.video_links||[];if(links.length){const h=document.createElement('h3');h.textContent='روابط الفيديو';body.append(h);links.forEach(item=>{const a=document.createElement('a');a.href=item.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=item.label||item.url;body.append(a)})}$('#preview-dialog').showModal()}
  async function renderMedia(){
    const lessons=await api('/api/admin/lessons?page_size=100');
    if(!lessons.items.length){$('#main-content').innerHTML=heading('الملفات والفيديو','ارفع ملفات الدروس وأضف روابط الفيديو.')+emptyState('لا توجد دروس','أنشئ درسًا أولًا لإدارة وسائطه.');return}
    const selected=lessons.items.find(x=>x.id===state.filter)||lessons.items[0];state.filter=selected.id;
    const files=await api(`/api/admin/lessons/${selected.id}/files`);
    const links=selected.content_metadata?.video_links||[];
    const actions=`${can('files.upload')?'<button class="button button-primary" id="upload-file">↑ رفع ملف</button>':''}${can('images.manage')?'<button class="button button-quiet" id="upload-image">＋ رفع صورة</button>':''}${can('videos.add_link')?'<button class="button button-quiet" id="add-video">＋ رابط فيديو</button>':''}`;
    $('#main-content').innerHTML=heading('الملفات والفيديو','موارد مرتبطة مباشرة بإصدار الدرس الحالي.',actions)+toolbar({search:true,status:false,select:'اختر الدرس',selectOptions:lessons.items.map(x=>({id:x.id,title:x.title}))})+`<div class="content-layout"><section class="content-card"><h3>الملفات المرفقة <span class="nav-count">${files.length}</span></h3>${files.length?files.map(f=>fileRow(f,'assets')).join(''):emptyState('لا توجد ملفات','ارفع PDF أو ملفًا تعليميًا لربطه بهذا الدرس.')}</section><section class="content-card"><h3>روابط الفيديو <span class="nav-count">${links.length}</span></h3>${links.length?links.map(v=>`<div class="video-row"><span class="file-icon">▶</span><span class="file-info"><strong>${esc(v.label||'فيديو')}</strong><small>${esc(v.url)}</small></span><a class="button button-small" href="${esc(v.url)}" target="_blank" rel="noopener noreferrer">فتح</a>${can('videos.manage')?`<button class="button button-small button-danger" data-delete-video="${esc(v.id)}">حذف</button>`:''}</div>`).join(''):'<p>لا توجد روابط فيديو لهذا الدرس بعد.</p>'}</section><section class="content-card"><h3>الصورة المصاحبة</h3><p>تُخزن الصور ضمن إصدار الدرس، وتتطلب صلاحية <code>images.manage</code>.</p><div id="image-list">${(selected.content_metadata?.images||[]).length?(selected.content_metadata.images).map(f=>fileRow(f,'images')).join(''):'<p>لا توجد صور مرفقة.</p>'}</div></section></div>`;
    attachFilters();
    $('#upload-file')?.addEventListener('click',()=>chooseAndUpload(selected.id,'assets'));
    $('#upload-image')?.addEventListener('click',()=>chooseAndUpload(selected.id,'images'));
    $('#add-video')?.addEventListener('click',()=>showForm({title:'إضافة رابط فيديو',fields:[{name:'label',label:'اسم الفيديو',value:'شرح الدرس'},{name:'url',label:'رابط HTTPS',required:true,placeholder:'https://…'}],onSubmit:async d=>{await api(`/api/admin/lessons/${selected.id}/videos`,{method:'POST',body:JSON.stringify(d)});toast('تمت إضافة رابط الفيديو');renderSection()}}));
    $$('[data-download]').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;try{const headers={};if(initData)headers['X-Telegram-Init-Data']=initData;const response=await fetch(`/api/admin/files/${encodeURIComponent(b.dataset.download)}`,{headers,credentials:'same-origin'});if(!response.ok)throw new Error(response.status===403?'لا تملك صلاحية عرض الملف.':'تعذر تنزيل الملف.');const blob=await response.blob();const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=b.dataset.filename||'download';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(error){toast(error.message,'error')}finally{b.disabled=false}}));
    $$('[data-delete-asset]').forEach(b=>b.addEventListener('click',()=>confirmAction('إزالة الملف؟','سيُزال الملف من الإصدار الحالي. تبقى الإصدارات السابقة محفوظة وغير قابلة للتنزيل من الواجهة.',async()=>{const bucket=b.dataset.category==='images'?'images':'files';await api(`/api/admin/lessons/${selected.id}/${bucket}/${b.dataset.deleteAsset}`,{method:'DELETE'});toast('تمت إزالة الملف');renderSection()})));
    $$('[data-delete-video]').forEach(b=>b.addEventListener('click',()=>confirmAction('إزالة رابط الفيديو؟','سيُنشأ إصدار محتوى جديد دون هذا الرابط.',async()=>{await api(`/api/admin/lessons/${selected.id}/videos/${b.dataset.deleteVideo}`,{method:'DELETE'});toast('تم حذف الرابط');renderSection()})));
  }
  function fileRow(file,category){const mayDelete=category==='images'?can('images.manage'):can('files.delete');return `<div class="file-row"><span class="file-icon">${file.content_type==='application/pdf'?'PDF':category==='images'?'▧':'↧'}</span><span class="file-info"><strong>${esc(file.filename)}</strong><small>${formatBytes(file.size)} · ${esc(file.content_type)}</small></span><button class="button button-small" data-download="${esc(file.id)}" data-filename="${esc(file.filename)}">تنزيل</button>${mayDelete?`<button class="button button-small button-danger" data-delete-asset="${esc(file.id)}" data-category="${category}">إزالة</button>`:''}</div>`}
  function formatBytes(size){if(size<1024)return `${size} B`;if(size<1024*1024)return `${(size/1024).toFixed(0)} KB`;return `${(size/1024/1024).toFixed(1)} MB`}
  async function chooseAndUpload(lessonId,category){const picker=$('#file-picker');picker.accept=category==='images'?'.png,.jpg,.jpeg,.webp':'.pdf,.png,.jpg,.jpeg,.webp,.txt,.md,.docx,.pptx,.xlsx';picker.onchange=async()=>{const file=picker.files?.[0];if(!file)return;if(file.size>20*1024*1024){toast('الحد الأقصى لحجم الملف 20 MB.','error');picker.value='';return}const form=new FormData();form.append('file',file);const button=category==='images'?$('#upload-image'):$('#upload-file');if(button){button.disabled=true;button.textContent='جارٍ الرفع…'}try{await api(`/api/admin/lessons/${lessonId}/${category==='images'?'images':'files'}`,{method:'POST',body:form});toast('تم رفع الملف وربطه بالدرس');renderSection()}catch(error){toast(error.message,'error')}finally{if(button){button.disabled=false;button.textContent=category==='images'?'＋ رفع صورة':'↑ رفع ملف'}picker.value=''}};picker.click()}
  async function renderRoles(){
    const canAdmins=can('admins.manage'),canPermissions=can('permissions.manage');
    if(!canAdmins&&!canPermissions){$('#main-content').innerHTML=heading('المشرفون والصلاحيات','')+emptyState('لا توجد صلاحية لإدارة المشرفين','هذا القسم مخصص لحسابات الإدارة المخولة.');return}
    const [adminData,roleData,permissionData]=await Promise.all([
      canAdmins?loadPage('admins'):{items:[],page:1,page_size:20,total:0,pages:0},
      canPermissions?api('/api/admin/roles'):{items:[]},
      canPermissions?api('/api/admin/permissions'):{items:[]}
    ]);
    state.adminRows=adminData.items||[];state.roles=roleData.items||[];state.roleNames=state.roles.map(r=>r.name);state.permissionCatalog=permissionData.items||[];
    const actions=`${canAdmins&&canPermissions?'<button class="button button-primary" id="new-admin">＋ إضافة Admin</button>':''}${canPermissions?'<button class="button button-quiet" id="new-role">＋ إنشاء Role</button><button class="button button-quiet" id="assign-role">إسناد Role</button><button class="button button-quiet" id="user-override">تجاوز مستخدم</button>':''}`;
    const adminRows=state.adminRows.map(admin=>{
      const root=admin.roles.includes('SUPER_ADMIN'),self=admin.telegram_id===state.userId;
      const roleTags=admin.roles.length?admin.roles.map(role=>`<span class="permission-tag">${esc(role)}</span>`).join(''):'<span class="secondary-cell">لا يوجد Role نشط</span>';
      const stateTag=admin.enabled?'<span class="status-pill status-published">نشط</span>':'<span class="status-pill status-draft">معطّل</span>';
      const controls=`<div class="row-actions"><button class="button button-small" data-admin-audit="${admin.telegram_id}">سجل النشاط</button>${!self&&canAdmins&&canPermissions?`<button class="button button-small" data-admin-role="${admin.telegram_id}">تغيير Role</button>`:''}${!self&&canPermissions?`<button class="button button-small" data-admin-permissions="${admin.telegram_id}">الصلاحيات (${admin.permissions.length})</button>`:''}${!self&&!root&&canAdmins?`<button class="button button-small ${admin.enabled?'button-danger':''}" data-admin-toggle="${admin.telegram_id}" data-enabled="${admin.enabled?'true':'false'}">${admin.enabled?'تعطيل':'إعادة تفعيل'}</button>`:''}</div>`;
      return `<tr><td class="primary-cell">${esc(admin.username||'—')}<span class="secondary-cell">Telegram ID ${admin.telegram_id}${self?' · حسابك':''}</span></td><td>${roleTags}</td><td>${stateTag}</td><td>${Number(admin.permissions.length).toLocaleString('ar')}</td><td>${admin.last_activity?esc(new Date(admin.last_activity).toLocaleString('ar')):'لا يوجد نشاط إداري مسجل'}</td><td>${controls}</td></tr>`;
    }).join('');
    const adminPanel=canAdmins?`<section class="panel admin-management-panel"><div class="panel-header"><div><h2>حسابات المشرفين</h2><p>الأدوار والصلاحيات وحالة الوصول وآخر نشاط إداري.</p></div></div>${toolbar({status:false})}${adminData.items.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>الحساب</th><th>Roles</th><th>الحالة</th><th>الصلاحيات</th><th>آخر نشاط</th><th>إجراءات</th></tr></thead><tbody>${adminRows}</tbody></table></div>${pagination(adminData)}`:emptyState('لا توجد حسابات Admin','ابحث عن مستخدم مسجل باستخدام Telegram ID، ثم امنحه Role إداريًا.')}</section>`:'';
    const rolePanel=canPermissions?`<section class="panel"><div class="panel-header"><div><h2>Roles & Permissions</h2><p>أدوار قابلة للتوسع، مع منح أو سحب Permission على مستوى Role.</p></div></div><div class="role-grid">${state.roles.map(r=>`<article class="role-card"><h3><span>${esc(r.name)}</span><span class="status-pill">${r.is_system?'نظامي':'مخصص'}</span></h3><p>${esc(r.description||'—')}</p><div class="permission-tags">${r.permissions.slice(0,14).map(p=>`<span class="permission-tag">${esc(p)}</span>`).join('')}${r.permissions.length>14?`<span class="permission-tag">+${r.permissions.length-14}</span>`:''}${r.permissions.length?'':'<span class="permission-tag">بدون صلاحيات مباشرة</span>'}</div>${!r.is_system?`<div class="row-actions" style="margin-top:13px"><button class="button button-small" data-role-permission="${esc(r.name)}">إضافة/سحب Permission</button></div>`:''}</article>`).join('')}</div></section>`:'';
    $('#main-content').innerHTML=heading('المشرفون والصلاحيات','إدارة حسابات Admin، أدوارها، صلاحياتها المباشرة، وآثارها الإدارية.',actions)+adminPanel+rolePanel;
    if(canAdmins&&adminData.items.length){attachFilters();attachPagination(adminData)}
    $('#new-admin')?.addEventListener('click',createAdmin);
    $('#new-role')?.addEventListener('click',()=>showForm({title:'إنشاء Role جديد',fields:[{name:'name',label:'اسم الدور',required:true,placeholder:'VIDEO_CURATOR'},{name:'description',label:'الوصف',type:'textarea'}],onSubmit:async d=>{await api('/api/admin/roles',{method:'POST',body:JSON.stringify(d)});toast('تم إنشاء الدور');renderSection()}}));
    $('#assign-role')?.addEventListener('click',()=>showForm({title:'إسناد Role لمستخدم',fields:[{name:'telegram_id',label:'Telegram User ID',type:'number',required:true},{name:'role_name',label:'الدور',type:'select',required:true,options:state.roleNames.map(r=>({value:r,label:r}))},{name:'expires_at',label:'انتهاء الإسناد (ISO-8601 اختياري)',placeholder:'2027-01-01T00:00:00+00:00'}],onSubmit:async d=>{await api(`/api/admin/users/${encodeURIComponent(d.telegram_id)}/roles`,{method:'POST',body:JSON.stringify({role_name:d.role_name,expires_at:d.expires_at||null})});toast('تم إسناد الدور');renderSection()}}));
    $('#user-override')?.addEventListener('click',()=>showForm({title:'تجاوز صلاحية لمستخدم',fields:[{name:'telegram_id',label:'Telegram User ID',type:'number',required:true},{name:'permission',label:'مفتاح permission',required:true,placeholder:'lessons.edit'},{name:'granted',label:'قرار الصلاحية',type:'select',value:'true',options:[{value:'true',label:'منح'},{value:'false',label:'منع'}]},{name:'expires_at',label:'انتهاء التجاوز (ISO-8601 اختياري)'}],onSubmit:async d=>{await api(`/api/admin/users/${encodeURIComponent(d.telegram_id)}/permissions`,{method:'PUT',body:JSON.stringify({permission:d.permission,granted:d.granted==='true',expires_at:d.expires_at||null})});toast('تم تحديث التجاوز الفردي')}}));
    $$('[data-role-permission]').forEach(b=>b.addEventListener('click',()=>showForm({title:`تعديل صلاحيات ${b.dataset.rolePermission}`,fields:[{name:'permission',label:'مفتاح permission',required:true,placeholder:'courses.edit'},{name:'granted',label:'القرار',type:'select',value:'true',options:[{value:'true',label:'منح'},{value:'false',label:'سحب'}]}],onSubmit:async d=>{await api(`/api/admin/roles/${encodeURIComponent(b.dataset.rolePermission)}/permissions`,{method:'PUT',body:JSON.stringify({permission:d.permission,granted:d.granted==='true'})});toast('تم تحديث صلاحية الدور');renderSection()}})));
    $$('[data-admin-role]').forEach(b=>b.addEventListener('click',()=>changeAdminRole(state.adminRows.find(a=>a.telegram_id===Number(b.dataset.adminRole)))));
    $$('[data-admin-toggle]').forEach(b=>b.addEventListener('click',()=>toggleAdmin(state.adminRows.find(a=>a.telegram_id===Number(b.dataset.adminToggle)))));
    $$('[data-admin-permissions]').forEach(b=>b.addEventListener('click',()=>manageAdminPermissions(state.adminRows.find(a=>a.telegram_id===Number(b.dataset.adminPermissions)))));
    $$('[data-admin-audit]').forEach(b=>b.addEventListener('click',()=>showAdminAudit(state.adminRows.find(a=>a.telegram_id===Number(b.dataset.adminAudit)))));
  }
  async function createAdmin(){
    if(!state.roles.length){toast('أنشئ Role مناسبًا أولًا.','error');return}
    await showForm({title:'إضافة Admin',fields:[
      {name:'telegram_id',label:'Telegram ID لمستخدم مسجل',type:'number',required:true},
      {name:'role_name',label:'Role',type:'select',required:true,options:state.roleNames.map(r=>({value:r,label:r}))},
      {name:'permissions',label:'Permissions إضافية (اختياري)',type:'multiselect',options:state.permissionCatalog.map(p=>({value:p.key,label:p.key}))}
    ],onSubmit:async data=>{await api('/api/admin/admins',{method:'POST',body:JSON.stringify({telegram_id:Number(data.telegram_id),role_name:data.role_name,permissions:data.permissions||[]})});toast('تم إنشاء حساب Admin وتسجيل العملية');state.page=1;renderSection()}})
  }
  async function changeAdminRole(admin){
    if(!admin)return;
    await showForm({title:`تغيير Role · ${admin.telegram_id}`,fields:[{name:'role_name',label:'Role الجديد',type:'select',required:true,value:admin.roles[0]||'',options:state.roleNames.map(r=>({value:r,label:r}))}],onSubmit:async data=>{await api(`/api/admin/admins/${admin.telegram_id}/role`,{method:'PATCH',body:JSON.stringify(data)});toast('تم تحديث Role');renderSection()}})
  }
  function toggleAdmin(admin){
    if(!admin)return;
    const enabled=!admin.enabled;
    confirmAction(enabled?'إعادة تفعيل Admin؟':'تعطيل Admin؟',enabled?`سيُعاد السماح للمستخدم ${admin.telegram_id} بالدخول وفق صلاحياته.`:`سيفقد المستخدم ${admin.telegram_id} كل صلاحيات Admin فورًا، مع الاحتفاظ بسجل التدقيق.`,async()=>{await api(`/api/admin/admins/${admin.telegram_id}/status`,{method:'PATCH',body:JSON.stringify({enabled})});toast(enabled?'تمت إعادة تفعيل Admin':'تم تعطيل Admin');renderSection()})
  }
  async function refreshAdminPermissions(adminId){
    const params=new URLSearchParams({page:'1',page_size:'100',q:String(adminId)});
    const data=await api(`/api/admin/admins?${params}`);
    const updated=data.items.find(a=>a.telegram_id===adminId);if(!updated)throw new Error('لم يعد حساب Admin ظاهرًا.');
    const index=state.adminRows.findIndex(a=>a.telegram_id===adminId);if(index>=0)state.adminRows[index]=updated;
    fillAdminPermissions(updated)
  }
  function fillAdminPermissions(admin){
    const dialog=$('#admin-permission-dialog');$('#admin-permission-title').textContent=`Permissions · ${admin.username||admin.telegram_id}`;
    const effective=new Set(admin.permissions||[]),overrides=new Map((admin.overrides||[]).map(item=>[item.permission,item.granted]));
    const keys=[...new Set([...effective,...[...overrides].filter(([,granted])=>!granted).map(([key])=>key)])].sort();
    const container=$('#admin-permission-items');container.innerHTML=keys.length?keys.map(key=>{
      const active=effective.has(key),direct=overrides.has(key),source=direct?(overrides.get(key)?'منح مباشر':'حظر مباشر'):'من Role';
      return `<div class="admin-permission-row"><div><strong>${esc(key)}</strong><small>${source}${active?' · فعّالة':' · غير فعّالة'}</small></div><button type="button" class="button button-small ${active?'button-danger':''}" data-permission-key="${esc(key)}" data-permission-grant="${active?'false':'true'}">${active?'إزالة':'منح'}</button></div>`
    }).join(''):'<div class="empty-state compact-empty"><h3>لا توجد صلاحيات فعّالة</h3></div>';
    const select=$('#admin-permission-select');select.innerHTML=state.permissionCatalog.map(item=>`<option value="${esc(item.key)}">${esc(item.key)}</option>`).join('');
    $('#admin-permission-grant').onclick=()=>{const key=select.value;if(key)changeAdminPermission(admin.telegram_id,key,true)};
    container.onclick=event=>{const button=event.target.closest('[data-permission-key]');if(button)changeAdminPermission(admin.telegram_id,button.dataset.permissionKey,button.dataset.permissionGrant==='true')};
  }
  function manageAdminPermissions(admin){
    if(!admin)return;fillAdminPermissions(admin);const dialog=$('#admin-permission-dialog');if(!dialog.open)dialog.showModal()
  }
  function changeAdminPermission(adminId,key,granted){
    confirmAction(granted?'منح Permission؟':'إزالة Permission؟',`${granted?'سيُمنح':'ستُحجب'} ${key} للمشرف ${adminId}. هذا التغيير سيُسجل في Audit Log.`,async()=>{await api(`/api/admin/admins/${adminId}/permissions`,{method:'PUT',body:JSON.stringify({permission:key,granted})});toast(granted?'تم منح الصلاحية':'تم حجب الصلاحية');await refreshAdminPermissions(adminId)})
  }
  async function showAdminAudit(admin){
    if(!admin)return;const data=await api(`/api/admin/admins/${admin.telegram_id}/audit?limit=100`);
    $('#preview-title').textContent=`آخر النشاط الإداري · ${admin.username||admin.telegram_id}`;const body=$('#preview-content');body.replaceChildren();
    if(!data.items.length){const empty=document.createElement('p');empty.textContent='لا توجد أحداث لهذا المشرف بعد.';body.append(empty)}
    for(const item of data.items){const article=document.createElement('article');article.className='audit-item';const action=document.createElement('strong');action.textContent=item.action;const resource=document.createElement('span');resource.textContent=`${item.resource_type}${item.resource_key?' · '+item.resource_key:''}`;const date=document.createElement('small');date.textContent=new Date(item.occurred_at).toLocaleString('ar');const outcome=document.createElement('span');outcome.textContent=item.outcome==='SUCCESS'?'ناجح':'فشل';article.append(action,resource,date,outcome);body.append(article)}
    $('#preview-dialog').showModal()
  }
  async function renderAudit(){const data=await api('/api/admin/audit?limit=100');$('#main-content').innerHTML=heading('الأمان وسجل التدقيق','أحداث إدارية مع النتيجة والمورد والمصدر، دون حفظ أسرار أو محتوى حساس.')+`<div class="panel"><div class="panel-header"><div><h2>الأحداث الأخيرة</h2><p>${data.items.length} سجلًا · أحدث الأحداث أولًا</p></div><button class="button button-quiet" id="refresh-audit">تحديث</button></div><div class="panel-body">${data.items.length?`<div class="audit-list">${data.items.map(e=>`<article class="audit-item"><div><strong>${esc(e.action)}</strong><small>${esc(e.occurred_at)}</small></div><div><strong>${esc(e.resource_type)}${e.resource_key?` · ${esc(e.resource_key)}`:''}</strong><small>${esc(e.resource_id||'')}</small></div><div>${e.outcome==='SUCCESS'?'<span class="status-pill status-published">ناجح</span>':'<span class="status-pill status-draft">فشل</span>'}</div><div><strong>UID ${esc(e.actor_user_id??'—')}</strong><small>${esc(e.ip_address||'IP غير متاح')} · ${esc(e.user_agent||'')}</small></div></article>`).join('')}</div>`:emptyState('لا توجد أحداث بعد','ستظهر هنا عمليات الإدارة ومحاولات الوصول المرفوضة.')}</div></div>`;$('#refresh-audit').addEventListener('click',renderSection)}
  function renderPlaceholder(){const section=state.section;$('#main-content').innerHTML=heading(names[section]||'الإدارة','إعدادات ومساحات الإدارة حسب صلاحيات حسابك.')+`<div class="content-layout"><section class="content-card"><div class="notice"><span class="notice-icon">◌</span><div><strong>القسم ظاهر حسب صلاحيتك</strong><p>واجهة هذا المجال لا تحتوي بعد على عمليات مرتبطة بمصدر البيانات الحالي. لم يتم عرض بيانات تجريبية أو إنشاء عمليات صورية.</p></div></div><h3 style="margin-top:18px">${esc(names[section]||'')}</h3><p>سيتم ربط هذا القسم بخدمة المجال الخاصة به في مرحلة لاحقة. تبقى نقاط الـAPI غير المسجلة مغلقة افتراضيًا بوساطة Authorization Middleware.</p></section><section class="content-card"><h3>حدود الوصول</h3><div class="permission-tags">${(permissionFor[section]||[]).filter(can).map(p=>`<span class="permission-tag">${esc(p)}</span>`).join('')||'<span class="permission-tag">لا توجد صلاحية فعّالة</span>'}</div></section></div>`}
  function attachOrdering(entity,rows,parentField){
    $$('[data-move]').forEach(button=>button.addEventListener('click',async()=>{const parentId=button.dataset.parent;if(!parentId){toast('تعذر تحديد الحاوية للترتيب.','error');return}button.disabled=true;try{await api(`/api/admin/${entity}/order`,{method:'POST',body:JSON.stringify({parent_id:parentId,item_id:button.dataset.id,direction:button.dataset.move})});toast('تم تحديث الترتيب');renderSection()}catch(error){toast(error.message,'error')}finally{button.disabled=false}}));
  }
  async function showForm({title,fields,onSubmit,submitLabel='حفظ'}){
    const dialog=$('#editor-dialog'),container=$('#dialog-fields'),submit=$('#dialog-submit');$('#dialog-title').textContent=title;submit.textContent=submitLabel;container.replaceChildren();
    for(const field of fields){const wrap=document.createElement('label');wrap.className='field-wrap';const caption=document.createElement('span');caption.className='field-label';caption.textContent=field.label;let input;
      if(field.type==='textarea'){input=document.createElement('textarea');input.className='field-control textarea'}else if(field.type==='select'||field.type==='multiselect'){input=document.createElement('select');input.className='field-control';input.multiple=field.type==='multiselect';if(input.multiple)input.size=Math.min(7,Math.max(3,(field.options||[]).length));for(const option of (field.options||[])){const el=document.createElement('option');el.value=option.value;el.textContent=option.label;if(Array.isArray(field.value)&&field.value.includes(option.value))el.selected=true;input.append(el)}}else{input=document.createElement('input');input.className='field-control';input.type=field.type==='number'?'number':'text';if(field.type==='number')input.min='0'}
      input.name=field.name;input.required=Boolean(field.required);input.placeholder=field.placeholder||'';if(field.value!==undefined&&field.type!=='multiselect')input.value=field.value;wrap.append(caption,input);container.append(wrap);
    }
    dialog.showModal();$('#editor-form').onsubmit=async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget).entries());for(const field of fields){if(field.type==='multiselect')data[field.name]=[...event.currentTarget.elements[field.name].selectedOptions].map(option=>option.value)}const submitButton=$('#dialog-submit');submitButton.disabled=true;submitButton.innerHTML='<span class="spinner"></span> جارٍ الحفظ';try{await onSubmit(data);dialog.close()}catch(error){toast(error.message,'error')}finally{submitButton.disabled=false;submitButton.textContent=submitLabel}};
  }
  function confirmAction(title,message,action){$('#confirm-title').textContent=title;$('#confirm-message').textContent=message;const dialog=$('#confirm-dialog');dialog.showModal();$('#confirm-form').onsubmit=async event=>{event.preventDefault();const submit=$('#confirm-submit');if(event.submitter?.value!=='confirm'){dialog.close();return}submit.disabled=true;submit.textContent='جارٍ التنفيذ…';try{await action();dialog.close()}catch(error){toast(error.message,'error')}finally{submit.disabled=false;submit.textContent='تأكيد'}}}
  document.addEventListener('keydown',event=>{if(event.key==='Escape')toggleSidebar(false)});
  boot();
})();
